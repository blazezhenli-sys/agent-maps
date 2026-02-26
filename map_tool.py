import requests
import osm2geojson
import folium
import json
from geopy.geocoders import Nominatim

def get_city_geojson(city_query):
    """
    Taiwan-Specific Fetcher.
    Resolves city to OSM ID and fetches Level 7 Districts (區).
    """
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="taiwan_area_vibe_check")
    
    # 1. Resolve Location (e.g., "Taichung", "Taipei", "Kaohsiung")
    print(f"🌐 Resolving City: {city_query}...")
    locations = geolocator.geocode(city_query, exactly_one=False, limit=5)
    
    target_location = None
    for loc in locations:
        if loc.raw.get('osm_type') == 'relation':
            target_location = loc
            break
    if not target_location:
        target_location = locations[0]
        print(f"⚠️ No relation found. Using {target_location.raw.get('osm_type')}")
    else:
        print(f"✅ Found Relation ID: {target_location.raw.get('osm_id')}")

    osm_id = int(target_location.raw.get('osm_id'))
    print("OSM ID:", osm_id)
    # Taiwan Cities are Relations. Add 3.6B for the Overpass Area ID.

    # 2. Taiwan-Strict Query (Level 7 Districts only)
    # This avoids the '9 results' bug by skipping neighborhoods and targeting Districts.
    query = f"""
    [out:json][timeout:180];
    area({osm_id + 3600000000})->.cityArea;
    (
    // Strictly only Level 7 (Districts)
    relation["boundary"="administrative"]["admin_level"="7"](area.cityArea);
    );
    out geom; 
    """
    
    print(f"🌍 Fetching Level 7 Districts for {city_query}...")
    try:
        response = requests.get(overpass_url, params={'data': query}, timeout=60)
        response.raise_for_status()
        
        # Convert to standard GeoJSON
        geojson_data = osm2geojson.json2geojson(response.json())
        return geojson_data, target_location
    except Exception as e:
        print(f"❌ OSM Fetch Error: {e}")
        return None, None

import os
import json
import pandas as pd
import folium
def generate_choropleth(cities, topic):

    if not cities:
        return None

    base_map = None
    valid_city_added = False

    for city in cities:

        data_file = f"{city}_{topic}_data.json"
        geo_file = f"{city}_{topic}_map.geojson"

        if not (os.path.exists(data_file) and os.path.exists(geo_file)):
            print(f"Missing files for {city}")
            continue

        with open(data_file, "r") as f:
            mapping_data = json.load(f)

        with open(geo_file, "r") as f:
            geojson_data = json.load(f)

        if not geojson_data.get("features"):
            continue

        df = pd.DataFrame(list(mapping_data.items()), columns=["name", "value"])

        # ─────────────────────────────
        # Normalize properties + inject score
        # ─────────────────────────────
        score_lookup = dict(mapping_data)

        for feature in geojson_data["features"]:
            props = feature["properties"]

            # safely extract district name
            district = None
            if "tags" in props:
                district = props["tags"].get("name:en") or props["tags"].get("name")
            else:
                district = props.get("name")

            feature["properties"]["district"] = district
            feature["properties"]["score"] = score_lookup.get(district, None)

        # ─────────────────────────────
        # Initialize map
        # ─────────────────────────────
        if base_map is None:
            first_feature = geojson_data["features"][0]
            geometry = first_feature["geometry"]

            if geometry["type"] == "Polygon":
                lon, lat = geometry["coordinates"][0][0]
            elif geometry["type"] == "MultiPolygon":
                lon, lat = geometry["coordinates"][0][0][0]
            else:
                raise ValueError(f"Unsupported geometry type: {geometry['type']}")

            base_map = folium.Map(
                location=[lat, lon],
                zoom_start=10,
                tiles="cartodbpositron"
            )

        # ─────────────────────────────
        # Choropleth (color layer)
        # ─────────────────────────────
        folium.Choropleth(
            geo_data=geojson_data,
            data=df,
            columns=["name", "value"],
            key_on="feature.properties.district",  # safer
            fill_color="RdYlGn",
            fill_opacity=0.7,
            line_opacity=0.4,
            legend_name=f"{city} {topic} Index",
            nan_fill_color="gray",
            name=city,
            overlay=True,
            control=True,
            show=True
        ).add_to(base_map)

        # ─────────────────────────────
        # Hover layer (interaction layer)
        # ─────────────────────────────
        folium.GeoJson(
            geojson_data,
            name=f"{city} hover",
            style_function=lambda x: {
                "fillColor": "transparent",
                "color": "black",
                "weight": 1,
            },
            highlight_function=lambda x: {
                "weight": 3,
                "color": "blue",
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["district", "score"],
                aliases=["District:", f"{topic.capitalize()} Score:"],
                localize=True,
            ),
        ).add_to(base_map)

        valid_city_added = True

    if not valid_city_added:
        return None

    folium.LayerControl(collapsed=False).add_to(base_map)
    base_map.fit_bounds(base_map.get_bounds())

    return base_map