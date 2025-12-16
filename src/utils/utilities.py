import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from shapely.geometry import Point
import geopandas as gpd
import contextily as ctx
from typing import Any, Dict, List, Optional


def plot_clusters_on_basemap(
    locations,
    clusters,
    out_path="clusters_map.png",
    names=None,
    title=None,
):
    """
    Plot clustered points over a static basemap and save an image.
    Uses a legend to identify points instead of labels on the map.
    """
    crs_mercator = "EPSG:3857"
    crs_input = "EPSG:4326"
    provider_key = "CartoDB.Positron"
    figsize = (12, 12)  # Square figure to avoid stretching
    marker_size = 600   # Larger markers for better visibility
    dpi_save = 150

    # Normalize input into ordered lists
    if isinstance(locations, dict):
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
        coords = list(locations)
        if names is None:
            names = [f"P{i}" for i in range(len(coords))]

    # Clean up names for legend (remove city/country suffixes)
    clean_names = []
    for n in names:
        parts = n.split(',')
        clean_names.append(parts[0].strip())

    if len(coords) != len(clusters) or len(coords) != len(names):
        raise ValueError("coords, clusters and names must have the same length")

    # Build GeoDataFrame
    pts = [Point(lon, lat) for lon, lat in coords]
    gdf = gpd.GeoDataFrame({
        'name': names,
        'clean_name': clean_names,
        'cluster': clusters
    }, geometry=pts, crs=crs_input)

    gdf_3857 = gdf.to_crs(crs_mercator)

    # Color palette for days
    base_colors = ['#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#9B5DE5', '#F4A261', '#00B4D8', '#06D6A0']
    unique_clusters = sorted(set(clusters))
    color_map = {c: base_colors[i % len(base_colors)] for i, c in enumerate(unique_clusters)}
    gdf_3857['color'] = gdf_3857['cluster'].map(color_map).fillna('black')

    # Create figure
    fig, ax = plt.subplots(figsize=figsize)

    # Compute extent
    minx, miny, maxx, maxy = gdf_3857.total_bounds
    dx = maxx - minx
    dy = maxy - miny
    buf = max(dx, dy) * 0.15 if dx > 0 or dy > 0 else 1000

    # Draw markers with numbers
    x_coords = list(gdf_3857.geometry.x)
    y_coords = list(gdf_3857.geometry.y)

    for idx, (x, y, cluster) in enumerate(zip(x_coords, y_coords, gdf_3857['cluster'])):
        color = color_map.get(cluster, 'gray')
        # Draw marker
        ax.scatter(x, y, c=color, s=marker_size, edgecolors='white', linewidths=3, zorder=5)
        # Draw number on marker
        ax.text(x, y, str(idx + 1), fontsize=16, fontweight='bold',
                ha='center', va='center', color='white', zorder=6)

    # Set limits
    ax.set_xlim(minx - buf, maxx + buf)
    ax.set_ylim(miny - buf, maxy + buf)

    # Add basemap
    try:
        provider = None
        try:
            provider = ctx.providers[provider_key]
        except Exception:
            top, _, sub = provider_key.partition('.')
            if hasattr(ctx.providers, top):
                top_bunch = getattr(ctx.providers, top)
                if sub and hasattr(top_bunch, sub):
                    provider = getattr(top_bunch, sub)
        if provider is None:
            provider = ctx.providers.get(provider_key, None)
        if provider:
            ctx.add_basemap(ax, source=provider, crs=crs_mercator)
    except Exception as e:
        print(f"⚠️ Could not add basemap: {e}")

    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=20, fontweight='bold', pad=20)

    # Create legend with attraction names grouped by day
    legend_elements = []
    for cluster_id in unique_clusters:
        color = color_map[cluster_id]
        # Add day header
        legend_elements.append(Line2D([0], [0], marker='o', color='w',
                                       markerfacecolor=color, markersize=14,
                                       label=f'Day {cluster_id + 1}'))
        # Add attractions for this day
        for idx, (name, c) in enumerate(zip(clean_names, clusters)):
            if c == cluster_id:
                legend_elements.append(Line2D([0], [0], marker='', color='w',
                                               label=f'  {idx + 1}. {name}'))

    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1),
              fontsize=11, framealpha=0.95, borderaxespad=0)

    try:
        fig.savefig(out_path, dpi=dpi_save, bbox_inches='tight', pad_inches=0.1)
        print(f"Saved map image to ./{out_path}")
    except Exception as e:
        print(f"⚠️ Could not save PNG: {e}")
    finally:
        plt.close(fig)


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
