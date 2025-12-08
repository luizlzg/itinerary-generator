import matplotlib.pyplot as plt
from shapely.geometry import Point
import geopandas as gpd
import contextily as ctx
from typing import Any, Dict

def plot_clusters_on_basemap(
    locations,
    clusters,
    out_path="clusters_map.png",
    names=None,
    title=None,
):
    """
    Plot clustered points over a static basemap and save an image.

    Parameters
    ----------
    locations : list or dict
        - If list/iterable: list of (lon, lat) pairs in that order.
        - If dict: mapping name -> {'lat': .., 'lon': ..} or name -> (lon, lat).
    clusters : list-like
        cluster labels for each location (same length and order as 'locations' list,
        or same order as dict.keys() if dict is provided).
    out_path : str, optional
        Path to save the output PNG image. Defaults to "clusters_map.png".
    names : list-like, optional
        labels for each point. If None and locations is dict, keys are used.
    title : str, optional
        Title for the plot. Defaults to "Clusters map".
    Returns
    -------
    fig, ax : matplotlib objects
    """

    crs_mercator = "EPSG:3857"
    crs_input = "EPSG:4326"
    provider_key="CartoDB.Positron"
    label_points=True
    figsize=(14, 10)
    marker_size=80
    color_map=None

    # Normalize input into ordered lists
    if isinstance(locations, dict):
        # locations dict: name -> (lon, lat) or {'lat':..,'lon':..}
        items = list(locations.items())
        if names is None:
            names = [k for k, _ in items]
        coords = []
        for k, v in items:
            if isinstance(v, dict):
                lat = v.get('lat') if 'lat' in v else v.get('latitude')
                lon = v.get('lon') if 'lon' in v else v.get('longitude')
                coords.append((lon, lat))
            elif isinstance(v, (list, tuple)) and len(v) == 2:
                coords.append((v[0], v[1]))
            else:
                raise ValueError("Dict values must be (lon, lat) or {'lat':..,'lon':..}")
    else:
        # locations is list-like of coords
        coords = list(locations)
        if names is None:
            names = [f"P{i}" for i in range(len(coords))]

    if len(coords) != len(clusters) or len(coords) != len(names):
        raise ValueError("coords, clusters and names must have the same length")

    # Build GeoDataFrame in input CRS
    pts = [Point(lon, lat) for lon, lat in coords]
    gdf = gpd.GeoDataFrame({'name': names, 'cluster': clusters}, geometry=pts, crs=crs_input)

    # Convert to web mercator for contextily
    gdf_3857 = gdf.to_crs(crs_mercator)

    # Color map: auto generate if not provided
    unique_clusters = sorted(set(clusters))
    if color_map is None:
        # simple palette: cycle through a few colors
        base_colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'cyan', 'magenta']
        color_map = {c: base_colors[i % len(base_colors)] for i, c in enumerate(unique_clusters)}
    gdf_3857['color'] = gdf_3857['cluster'].map(color_map).fillna('black')

    # Plot
    fig, ax = plt.subplots(figsize=figsize)
    gdf_3857.plot(ax=ax, marker='o', markersize=marker_size, alpha=0.85,
                  color=gdf_3857['color'], edgecolor='k', linewidth=0.35, zorder=3)

    if label_points:
        for x, y, label in zip(gdf_3857.geometry.x, gdf_3857.geometry.y, gdf_3857['name']):
            ax.text(x + 20, y + 20, label, fontsize=9, ha='left', va='bottom', zorder=5)

    # Compute extent buffer so tiles include context
    minx, miny, maxx, maxy = gdf_3857.total_bounds
    dx = maxx - minx
    dy = maxy - miny
    if dx == 0 and dy == 0:
        buf = 1000
    else:
        buf = max(dx, dy) * 0.25
    ax.set_xlim(minx - buf, maxx + buf)
    ax.set_ylim(miny - buf, maxy + buf)

    # Add basemap using the provider that worked for you (CartoDB.Positron by default)
    try:
        # Obtain provider object safely (works with different contextily/xyzservices versions)
        provider = None
        try:
            provider = ctx.providers[provider_key]
        except Exception:
            # try attribute-like names (older versions)
            top, _, sub = provider_key.partition('.')
            if hasattr(ctx.providers, top):
                top_bunch = getattr(ctx.providers, top)
                if sub and hasattr(top_bunch, sub):
                    provider = getattr(top_bunch, sub)
        if provider is None:
            # fallback: try direct string key in providers dict keys
            provider = ctx.providers.get(provider_key, None)

        if provider is None:
            raise RuntimeError(f"Provider '{provider_key}' not found in ctx.providers; try another key or run `list(ctx.providers.keys())` to inspect available providers.")

        ctx.add_basemap(ax, source=provider, crs=crs_mercator)
    except Exception as e:
        print("⚠️ Could not add basemap tiles. Error:", e)
        print("Plot will show points but without tiles.")

    ax.set_axis_off()
    if title is None:
        ax.set_title("Clustered locations — basemap", fontsize=14)
    else:
        ax.set_title(title, fontsize=14)
    plt.tight_layout()

    try:
        fig.savefig(out_path, dpi=300, bbox_inches='tight')
        print(f"Saved map image to ./{out_path}")
    except Exception as e:
        print("⚠️ Could not save PNG:", e)


def merge_dicts(left: Dict, right: Dict) -> Dict:
    """Merge two dictionaries, with right taking precedence."""
    if left is None:
        return right
    if right is None:
        return left
    return {**left, **right}


def replace_value(left: Any, right: Any) -> Any:
    """Replace left value with right value."""
    return right