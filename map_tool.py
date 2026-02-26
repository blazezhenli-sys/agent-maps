import requests
import osm2geojson
import folium
import json
from geopy.geocoders import Nominatim

def get_city_geojson(city_query):
    """
    Taiwan-Specific Fetcher.
    Resolves city to OSM ID and fetches Level 7 Districts (區).
    If no Level 7 results are found, it falls back to Level 8.
    """
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="taiwan_area_vibe_checker")
    
    # 1. Resolve Location
    print(f"🌐 Resolving City: {city_query}...")
    locations = geolocator.geocode(city_query, exactly_one=False, limit=5)

    if not locations:
        print(f"❌ Could not resolve city: {city_query}")
        return None, None
    
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
    area_id = osm_id + 3600000000  # For Overpass area query

    # 2. Query for administrative boundaries with fallback
    try:
        # First, try admin_level=7
        print(f"🌍 Fetching Level 7 Districts for {city_query}...")
        query_l7 = f"""
        [out:json][timeout:180];
        area({area_id})->.cityArea;
        (relation["boundary"="administrative"]["admin_level"="7"](area.cityArea););
        out geom; 
        """
        response = requests.get(overpass_url, params={'data': query_l7}, timeout=180)
        response.raise_for_status()
        geojson_data = osm2geojson.json2geojson(response.json())

        # If no features found, fallback to admin_level=8
        if not geojson_data.get("features"):
            print("⚠️ No results at Level 7. Trying Level 8...")
            query_l8 = f"""
            [out:json][timeout:180];
            area({area_id})->.cityArea;
            (relation["boundary"="administrative"]["admin_level"="8"](area.cityArea););
            out geom; 
            """
            response = requests.get(overpass_url, params={'data': query_l8}, timeout=180)
            response.raise_for_status()
            geojson_data = osm2geojson.json2geojson(response.json())

        return geojson_data, target_location

    except requests.exceptions.RequestException as e:
        print(f"❌ OSM Request Error: {e}")
        return None, None
    except Exception as e:
        print(f"❌ OSM Fetch or Conversion Error: {e}")
        return None, None
    
import json, folium, os, branca.colormap as cm
def generate_interactive_map(city, topic, scores, map_center=None, map_zoom=None, interactive=True):

    geo_file = f"{city}_{topic}_map.geojson"
    if not os.path.exists(geo_file):
        return None

    with open(geo_file) as f:
        geojson_data = json.load(f)

    # Attach scores and ensure 'district' property exists
    for feature in geojson_data["features"]:
        props = feature["properties"]
        district = (props.get("tags", {}).get("name:en") or
                    props.get("tags", {}).get("name") or
                    props.get("name") or
                    "Unnamed Area")  # Fallback for features with no name
        feature["properties"]["district"] = district
        feature["properties"]["score"] = scores.get(district)

    # Gradient colormap
    colormap = cm.LinearColormap(
        colors=["red", "orange", "yellow", "green"],
        vmin=0, vmax=1
    )
    colormap.caption = f"{topic.capitalize()} Score"

    def style_function(feature):
        score = feature["properties"]["score"]
        if score is None:
            return {"fillColor": "#ddd", "color": "black", "weight": 1, "fillOpacity": 0.4}
        return {"fillColor": colormap(score), "color": "black", "weight": 1, "fillOpacity": 0.75}

    # Use stored center/zoom if available
    m = folium.Map(
        location=map_center or [23.7, 121],
        zoom_start=map_zoom or 7,
        tiles="cartodbpositron",
        dragging=interactive,
        touch_zoom=interactive,
        scroll_wheel_zoom=interactive,
        double_click_zoom=interactive,
        zoom_control=interactive
    )

    folium.GeoJson(
        geojson_data,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["district", "score"],
            aliases=["District:", "Score:"],
            localize=True
        ),
        highlight_function=lambda x: {"weight": 3, "color": "blue"}
    ).add_to(m)

    colormap.add_to(m)
    return m