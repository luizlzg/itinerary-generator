"""Tools for the multi-agent itinerary generation graph."""
import json
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from typing_extensions import Annotated
from langgraph.types import Command
from src.mcp_client.tavily_client import TavilyMCPClient
from src.mcp_client.docx_client import LocalDocxGenerator
from src.utils.logger import LOGGER
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from sklearn.cluster import KMeans
import numpy as np


# Global clients (initialized on first use)
_tavily_client = None
_docx_generator = None
_geolocator = None


def get_geolocator():
    """Get or create geolocator for distance calculations."""
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="itinerary_generator")
    return _geolocator


def get_tavily_client():
    """Get or create Tavily MCP client."""
    global _tavily_client
    if _tavily_client is None:
        try:
            _tavily_client = TavilyMCPClient()
        except ValueError as e:
            LOGGER.warning(f"Warning: Tavily not configured: {e}")
            _tavily_client = None
    return _tavily_client


def get_docx_generator():
    """Get or create local DOCX generator."""
    global _docx_generator
    if _docx_generator is None:
        _docx_generator = LocalDocxGenerator()
    return _docx_generator


@tool
def search_attraction_info(
    query: str,
) -> str:
    """
    Web search tool to find information about attractions.
    Use this tool when you need to search for information online.

    Args:
        query: Search query

    Returns:
        JSON string with search results
    """
    client = get_tavily_client()
    if not client:
        return json.dumps({
            "error": "Tavily not configured. Set TAVILY_API_KEY in .env file",
        }, ensure_ascii=False)

    try:
        search_results = client.search(
            query,
            max_results=3,
            search_depth="advanced",
        )

        tool_output = search_results.get("results", [])
        tool_output = [{"url": res["url"], "title": res["title"], "content": res.get("content", "")} for res in tool_output]

        return json.dumps(tool_output, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Search error: {str(e)}",
        }, ensure_ascii=False)


@tool
def search_attraction_images(
    query: str,
    count: int = 5
) -> str:
    """
    Search for high-quality images of a tourist attraction using Tavily.

    Args:
        query: Search query (attraction name, city, etc.)
        count: Number of images to fetch (default: 5)

    Returns:
        JSON string with image URLs found
    """
    client = get_tavily_client()
    if not client:
        return json.dumps({
            "error": "Tavily not configured. Set TAVILY_API_KEY in .env file",
        }, ensure_ascii=False)

    try:
        search_data = client.search(
            query,
            max_results=3,
            search_depth="advanced",
            include_images=True,
            include_image_descriptions=True
        )

        images = search_data.get("images", [])

        result = {
            "images_found": len(images),
            "images": []
        }

        for img_object in images[:count]:
            result["images"].append({
                "url_regular": img_object["url"],
                "description": img_object["description"],
            })

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Image search error: {str(e)}",
        }, ensure_ascii=False)


@tool
def extract_coordinates(
    attraction_names: list[str],
    runtime: ToolRuntime,
) -> Command:
    """
    Extract geographic coordinates for a list of attractions using Nominatim.

    IMPORTANT: This tool updates the graph state with the obtained coordinates.
    The names you provide will be used EXACTLY as they are in the geocoding API.
    If some names fail, the tool will return which ones failed so you can try again.

    Args:
        attraction_names: List of NORMALIZED attraction names for geocoding
                          (e.g., ["Eiffel Tower, Paris, France", "Louvre Museum, Paris, France"])

    Returns:
        Command object that updates state with coordinates and returns success/failure info
    """
    geolocator = get_geolocator()

    # Get current state
    current_coordinates = runtime.state.get("attraction_coordinates", {})

    # Process new coordinates
    new_coordinates = {}
    failures = []

    for name in attraction_names:
        try:
            LOGGER.info(f"Geocoding: {name}")
            location = geolocator.geocode(name, timeout=10)

            if location:
                new_coordinates[name] = {
                    "lat": location.latitude,
                    "lon": location.longitude
                }
                LOGGER.info(f"✓ Success: {name} -> ({location.latitude}, {location.longitude})")
            else:
                failures.append(name)
                LOGGER.warning(f"✗ Failed: Could not find coordinates for '{name}'")

        except Exception as e:
            failures.append(name)
            LOGGER.error(f"✗ Error geocoding '{name}': {e}")

    # Merge new data with existing
    attraction_coordinates = {**current_coordinates, **new_coordinates}

    # Check if all coordinates are obtained (no failures)
    all_coordinates_obtained = len(failures) == 0

    # Create message for the agent
    message_content = json.dumps({
        "failures": failures,
        "total_success": len(new_coordinates),
        "total_failures": len(failures),
    }, ensure_ascii=False, indent=2)

    # Return Command to update state
    return Command(
        update={
            "attraction_coordinates": attraction_coordinates,
            "all_coordinates_obtained": all_coordinates_obtained,
            "messages": [ToolMessage(content=message_content, tool_call_id=runtime.tool_call_id)]
        }
    )


def _calculate_centroid(coordinates: dict, names: list) -> tuple:
    """Calculate the centroid (center point) for a list of attractions."""
    if not names:
        return None
    lats = [coordinates[name]["lat"] for name in names if name in coordinates]
    lons = [coordinates[name]["lon"] for name in names if name in coordinates]
    if not lats:
        return None
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _order_attractions_nearest_neighbor(coordinates: dict, attractions: list, starting_point: str = None) -> list:
    """
    Order attractions using nearest-neighbor algorithm.

    Algorithm:
    1. If starting_point is provided and valid, use it as the first attraction
    2. Otherwise, calculate the center (centroid) and start from the closest attraction to it
    3. From the current attraction, go to the nearest unvisited attraction
    4. Repeat until all attractions are visited

    Args:
        coordinates: Dict with {name: {lat, lon}} for each attraction
        attractions: List of attraction names to order
        starting_point: Optional attraction name to start the route from

    Returns:
        Ordered list of attraction names
    """
    if len(attractions) <= 1:
        return attractions

    # Filter attractions that have coordinates
    attractions_with_coords = [a for a in attractions if a in coordinates]
    if len(attractions_with_coords) <= 1:
        return attractions

    def distance_to_point(name, point):
        coord = (coordinates[name]["lat"], coordinates[name]["lon"])
        return geodesic(coord, point).km

    # Determine starting point
    if starting_point and starting_point in attractions_with_coords:
        # User specified a valid starting point
        first_attraction = starting_point
        LOGGER.info(f"Using user-specified starting point: {starting_point}")
    else:
        # Default: find attraction closest to centroid
        centroid = _calculate_centroid(coordinates, attractions_with_coords)
        if not centroid:
            return attractions
        first_attraction = min(attractions_with_coords, key=lambda a: distance_to_point(a, centroid))
        LOGGER.info(f"Using centroid-based starting point: {first_attraction}")

    # Nearest-neighbor traversal
    ordered = [first_attraction]
    remaining = set(attractions_with_coords) - {first_attraction}

    while remaining:
        current = ordered[-1]
        current_coord = (coordinates[current]["lat"], coordinates[current]["lon"])

        # Find nearest unvisited attraction
        nearest = min(remaining, key=lambda a: distance_to_point(a, current_coord))
        ordered.append(nearest)
        remaining.remove(nearest)

    # Add any attractions without coordinates at the end
    attractions_without_coords = [a for a in attractions if a not in coordinates]
    ordered.extend(attractions_without_coords)

    return ordered


def _validate_day_assignments(assignments: dict, num_days: int, param_name: str) -> tuple[bool, str]:
    """Validate day assignments are integers within valid range."""
    for name, day in assignments.items():
        if not isinstance(day, int):
            return False, f"{param_name}: day for '{name}' must be integer, got {type(day).__name__}"
        if day < 1:
            return False, f"{param_name}: day for '{name}' must be >= 1, got {day}"
        if day > num_days:
            return False, f"{param_name}: day for '{name}' must be <= {num_days}, got {day}"
    return True, ""


@tool
def organize_attractions_by_days(
    runtime: ToolRuntime,
    day_preferences: dict[str, int] = None,
    isolated_days: dict[str, int] = None,
    optimize_order_by_distance: bool = False,
    starting_point: str = None,
) -> Command:
    """
    Organize attractions by days intelligently.

    This tool adapts automatically to the scenario based on the provided parameters.

    IMPORTANT: All coordinates must have been obtained via 'extract_coordinates' first.

    Args:
        day_preferences: Optional dict with {attraction_name: day_number} for attractions that
                         MUST be on a specific day. The preference is ABSOLUTE - the attraction
                         goes to the specified day regardless of K-means.
                         Other flexible attractions can be added to the same day.
                         Example: {"Eiffel Tower, Paris": 1} - Eiffel Tower on day 1.

        isolated_days: Optional dict with {attraction_name: day_number} for attractions that
                       need an EXCLUSIVE day for themselves (no other attractions).
                       Example: {"Disneyland Paris": 1} - Day 1 is only for Disneyland,
                       K-means groups the others on remaining days.

        optimize_order_by_distance: If True, optimize the order of attractions within each day
                                    by geographic proximity (nearest-neighbor algorithm).
                                    Useful when user specifies all days but wants distance optimization.
                                    Default: False (preserve user's order when all days are predefined).

        starting_point: Optional attraction name to start the route from when optimizing by distance.
                        Must be one of the attractions in the coordinates.
                        Only used when optimize_order_by_distance=True.
                        Example: "Eiffel Tower, Paris" - start the optimized route from Eiffel Tower.

    Returns:
        Command that updates state with clusters and organization info.
    """
    try:
        num_days = runtime.state.get("num_days")
        coordinates = runtime.state.get("attraction_coordinates", {})
        all_coords_ok = runtime.state.get("all_coordinates_obtained", False)

        if not all_coords_ok:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": "Incomplete coordinates. Call extract_coordinates first."}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        if not coordinates:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": "No coordinates found. Call extract_coordinates first."}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        attraction_names = list(coordinates.keys())
        prefs = day_preferences or {}
        isolated = isolated_days or {}

        # Validate day numbers are integers and within range [1, num_days]
        valid, error_msg = _validate_day_assignments(prefs, num_days, "day_preferences")
        if not valid:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": error_msg}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        valid, error_msg = _validate_day_assignments(isolated, num_days, "isolated_days")
        if not valid:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": error_msg}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        # Validate attractions have coordinates
        all_defined = {**prefs, **isolated}
        attractions_without_coords = [n for n in all_defined.keys() if n not in coordinates]
        if attractions_without_coords:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": f"Attractions without coordinates: {attractions_without_coords}. Check the names."}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        # Identify attraction groups (isolated takes precedence over prefs)
        isolated_attractions = {n: d for n, d in isolated.items() if n in coordinates}
        attractions_with_pref = {n: d for n, d in prefs.items() if n in coordinates and n not in isolated_attractions}
        flexible_attractions = [n for n in attraction_names if n not in isolated_attractions and n not in attractions_with_pref]

        LOGGER.info(f"Organizing: {len(isolated_attractions)} isolated, {len(attractions_with_pref)} with preference, {len(flexible_attractions)} flexible, {num_days} days")

        # Days reserved for isolated attractions (no other attractions allowed)
        reserved_days = set(isolated_attractions.values())

        # Validate preferences don't target reserved days
        prefs_on_reserved_days = {n: d for n, d in attractions_with_pref.items() if d in reserved_days}
        if prefs_on_reserved_days:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({
                        "error": f"Conflict: preferences point to isolated days. "
                                 f"Attractions {list(prefs_on_reserved_days.keys())} want days {list(prefs_on_reserved_days.values())} "
                                 f"but those days are reserved for isolated attractions."
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        days_for_kmeans = [d for d in range(1, num_days + 1) if d not in reserved_days]

        # SCENARIO 1: All attractions have assigned days (all in prefs or isolated)
        if len(flexible_attractions) == 0:
            LOGGER.info(f"Scenario: All attractions have defined days (optimize_order_by_distance={optimize_order_by_distance})")
            # IMPORTANT: clusters must be aligned with attraction_names order (from coordinates.keys())
            # because the map visualization uses coordinates.keys() to iterate
            clusters = np.array([all_defined.get(n, 1) - 1 for n in attraction_names])

            # Group by day - preserve user's order from preferences (all_defined.keys())
            result_by_day_unordered = {}
            for n in all_defined.keys():
                day = all_defined.get(n, 1)
                result_by_day_unordered.setdefault(f"day_{day}", []).append(n)

            # Optionally optimize order within each day by distance
            if optimize_order_by_distance:
                result_by_day = {}
                for day_key, attractions in result_by_day_unordered.items():
                    # Only pass starting_point if it's in this day's attractions
                    day_starting_point = starting_point if starting_point in attractions else None
                    result_by_day[day_key] = _order_attractions_nearest_neighbor(coordinates, attractions, day_starting_point)
                mode_message = "Days predefined by user, order optimized by distance within each day."
                if starting_point:
                    mode_message += f" Starting from: {starting_point}."
            else:
                result_by_day = result_by_day_unordered
                mode_message = "User organization maintained."

            return Command(update={
                "clusters": clusters,
                "messages": [ToolMessage(
                    json.dumps({
                        "mode": "predefined",
                        "optimized_by_distance": optimize_order_by_distance,
                        "starting_point": starting_point,
                        "message": mode_message,
                        "days": result_by_day
                    }, ensure_ascii=False, indent=2),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        # SCENARIO 2: K-means clustering for flexible attractions only
        # Preferences are ABSOLUTE - they go directly to their day, not through K-means
        LOGGER.info(f"K-means on {len(flexible_attractions)} flexible attractions for {len(days_for_kmeans)} days")

        # Check if we have days available for flexible attractions
        # Days used by preferences (but not exclusive, so K-means can add more)
        days_with_pref = set(attractions_with_pref.values())
        # Days that are truly free (no isolated, no pref)
        free_days = [d for d in days_for_kmeans if d not in days_with_pref]

        # Total "slots" for K-means = days with prefs (can add more) + free days
        days_for_flex = list(days_with_pref) + free_days

        if not days_for_flex and flexible_attractions:
            return Command(update={
                "messages": [ToolMessage(
                    json.dumps({"error": "No days available to group flexible attractions."}, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        # Build final clusters array
        clusters = np.zeros(len(attraction_names), dtype=int)

        # First, assign isolated attractions to their exclusive days
        for idx, name in enumerate(attraction_names):
            if name in isolated_attractions:
                clusters[idx] = isolated_attractions[name] - 1

        # Second, assign attractions with preferences to their preferred days (ABSOLUTE)
        for idx, name in enumerate(attraction_names):
            if name in attractions_with_pref:
                clusters[idx] = attractions_with_pref[name] - 1

        # Third, K-means for flexible attractions
        if flexible_attractions:
            coords_flex = np.array([[coordinates[n]["lat"], coordinates[n]["lon"]] for n in flexible_attractions])
            n_clusters_flex = min(len(days_for_flex), len(flexible_attractions))

            if n_clusters_flex > 0:
                kmeans = KMeans(n_clusters=n_clusters_flex, random_state=42, n_init=10)
                clusters_flex = kmeans.fit_predict(coords_flex)

                # Map K-means clusters to available days
                # Prioritize days that already have preferences (to group nearby attractions)
                cluster_to_day = {}

                if attractions_with_pref:
                    # Calculate centroid of each preference day
                    pref_centroids = {}
                    for day in days_with_pref:
                        attractions_on_day = [n for n, d in attractions_with_pref.items() if d == day]
                        centroid = _calculate_centroid(coordinates, attractions_on_day)
                        if centroid:
                            pref_centroids[day] = centroid

                    # Calculate K-means cluster centers
                    kmeans_centers = {i: (kmeans.cluster_centers_[i][0], kmeans.cluster_centers_[i][1])
                                      for i in range(n_clusters_flex)}

                    # Greedy assignment: match clusters to nearest preference day or free day
                    assigned_clusters = set()
                    assigned_days = set()

                    # First pass: assign clusters to preference days by proximity
                    for day, pref_center in pref_centroids.items():
                        best_cluster = None
                        best_dist = float('inf')
                        for cid, center in kmeans_centers.items():
                            if cid not in assigned_clusters:
                                dist = geodesic(pref_center, center).km
                                if dist < best_dist:
                                    best_dist = dist
                                    best_cluster = cid
                        if best_cluster is not None:
                            cluster_to_day[best_cluster] = day
                            assigned_clusters.add(best_cluster)
                            assigned_days.add(day)

                    # Second pass: assign remaining clusters to free days
                    for cid in range(n_clusters_flex):
                        if cid not in assigned_clusters:
                            for day in free_days:
                                if day not in assigned_days:
                                    cluster_to_day[cid] = day
                                    assigned_days.add(day)
                                    break
                            else:
                                # Fallback: use any available day from days_for_flex
                                for day in days_for_flex:
                                    if day not in assigned_days:
                                        cluster_to_day[cid] = day
                                        assigned_days.add(day)
                                        break
                else:
                    # No preferences, just map clusters to available days
                    for i, day in enumerate(days_for_flex[:n_clusters_flex]):
                        cluster_to_day[i] = day

                # Assign flexible attractions based on K-means results
                for flex_idx, name in enumerate(flexible_attractions):
                    cid = clusters_flex[flex_idx]
                    day = cluster_to_day.get(cid, days_for_flex[0] if days_for_flex else 1)
                    name_idx = attraction_names.index(name)
                    clusters[name_idx] = day - 1

        # Build result grouped by day (unordered first)
        result_by_day_unordered = {}
        for idx, name in enumerate(attraction_names):
            day = clusters[idx] + 1
            result_by_day_unordered.setdefault(f"day_{day}", []).append(name)

        # Order attractions within each day using nearest-neighbor from center
        result_by_day = {}
        for day_key, attractions in result_by_day_unordered.items():
            # Only pass starting_point if it's in this day's attractions
            day_starting_point = starting_point if starting_point in attractions else None
            result_by_day[day_key] = _order_attractions_nearest_neighbor(coordinates, attractions, day_starting_point)

        message = "Attractions organized by geographic proximity. The order within each day is already optimized to minimize travel."
        if starting_point:
            message += f" Starting from: {starting_point}."

        return Command(update={
            "clusters": clusters,
            "messages": [ToolMessage(
                json.dumps({
                    "mode": "kmeans" if not isolated_attractions and not attractions_with_pref else "mixed",
                    "message": message,
                    "isolated_days": list(reserved_days) if reserved_days else None,
                    "starting_point": starting_point,
                    "days": result_by_day,
                }, ensure_ascii=False, indent=2),
                tool_call_id=runtime.tool_call_id
            )]
        })

    except Exception as e:
        LOGGER.error(f"Error organizing attractions: {e}", exc_info=True)
        return Command(update={
            "messages": [ToolMessage(
                json.dumps({"error": f"Error: {str(e)}"}, ensure_ascii=False),
                tool_call_id=runtime.tool_call_id
            )]
        })


@tool
def return_invalid_input_error(
    message: str,
    runtime: ToolRuntime,
) -> Command:
    """
    Use this tool when user input is INVALID or UNRELATED.

    Use cases:
    1. EMPTY INPUT: User didn't provide any attractions
    2. UNRELATED QUESTION: User asked something not about organizing itineraries
       (e.g., "What is the Eiffel Tower?", "Tell me about Paris")
    3. INPUT WITHOUT ATTRACTIONS: User wrote something but didn't mention tourist attractions

    IMPORTANT: This tool ENDS the flow. Use only when there's no way to proceed.

    Args:
        message: Explanatory message for the user about why the input is invalid
                 and what they should provide (polite and clear)

    Returns:
        Command that updates state with invalid_input=True and error_message
    """
    LOGGER.warning(f"Invalid input detected: {message}")

    return Command(update={
        "invalid_input": True,
        "error_message": message,
        "messages": [ToolMessage(
            json.dumps({
                "status": "invalid_input",
                "message": message
            }, ensure_ascii=False, indent=2),
            tool_call_id=runtime.tool_call_id
        )]
    })


# ============================================================================
# Tool Lists for Each Agent
# ============================================================================

# First agent (day organizer) - needs search, coordinate extraction, day organization, and error handling
DAY_ORGANIZER_TOOLS = [
    search_attraction_info,
    extract_coordinates,
    organize_attractions_by_days,
    return_invalid_input_error,
]

# Second agent (attraction researcher) - needs search and images
ATTRACTION_RESEARCHER_TOOLS = [
    search_attraction_info,
    search_attraction_images,
]
