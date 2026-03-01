import requests
import osm2geojson
import folium
import json
from geopy.geocoders import Nominatim
from country_configs import COUNTRY_CONFIGS

def ensure_geojson(city, topic, country="Taiwan"):
    """
    Ensures GeoJSON file exists for city.
    Uses country-specific district levels from COUNTRY_CONFIGS.
    Stores files under countries/<country>/<city>/map.geojson
    """
    # Prepare folder
    city_folder = os.path.join("countries", country, city)
    os.makedirs(city_folder, exist_ok=True)

    geo_file = os.path.join(city_folder, "map.geojson")
    data_file = os.path.join(city_folder, f"{topic}_data.json")  # for scores

    if not os.path.exists(geo_file):
        # Get country-specific district levels
        config = COUNTRY_CONFIGS.get(country, {})
        district_levels = config.get("district_levels", ["7", "8"])

        # Fetch GeoJSON (looping handled inside get_city_geojson)
        geojson_data_raw = get_city_geojson(city, country=country, district_levels=district_levels)
        if geojson_data_raw and geojson_data_raw[0]:
            geojson_data = geojson_data_raw[0]
        else:
            raise ValueError(f"Failed to fetch GeoJSON for {city}, {country}")

        # Save validated GeoJSON
        with open(geo_file, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, indent=4)

    return geo_file, data_file

def get_country_subareas(country_name):
    """
    Fetch all immediate subareas of a given country.
    Uses country-specific admin level from COUNTRY_CONFIGS.
    Returns GeoJSON and resolved Nominatim location.
    """
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="area_vibe_checker")
    
    config = COUNTRY_CONFIGS.get(country_name)
    if not config:
        raise ValueError(f"No configuration found for country '{country_name}'")
    admin_level = config.get("city_admin_level", "4")

    # 1️⃣ Resolve Country
    print(f"🌐 Resolving Country: {country_name}...")
    locations = geolocator.geocode(country_name, exactly_one=False, limit=5)
    if not locations:
        print(f"❌ Could not resolve country: {country_name}")
        return None, None

    target_location = next((loc for loc in locations if loc.raw.get('osm_type') == 'relation'), locations[0])
    print(f"✅ Using Relation ID: {target_location.raw.get('osm_id')}")

    osm_id = int(target_location.raw.get('osm_id'))
    area_id = osm_id + 3600000000

    # 2️⃣ Query subareas
    try:
        print(f"🌍 Fetching admin_level={admin_level} subareas for {country_name}...")
        query = f"""
        [out:json][timeout:300];
        area({area_id})->.countryArea;
        (relation["boundary"="administrative"]["admin_level"="{admin_level}"](area.countryArea););
        out geom;
        """
        response = requests.get(overpass_url, params={'data': query}, timeout=300)
        response.raise_for_status()
        geojson_data = osm2geojson.json2geojson(response.json())

        if not geojson_data.get("features"):
            print(f"⚠️ No features found at admin_level={admin_level} for {country_name}")

        return geojson_data, target_location

    except requests.exceptions.RequestException as e:
        print(f"❌ OSM Request Error: {e}")
        return None, None
    except Exception as e:
        print(f"❌ OSM Fetch or Conversion Error: {e}")
        return None, None

def get_city_geojson(city_query, country="Taiwan", district_levels=None):
    """
    Fetch GeoJSON for a city, trying country-specific district levels with fallbacks.
    district_levels: list of admin_levels to try (first is preferred)
    """
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="area_vibe_checker")
    # Use country config fallback if district_levels not provided
    if district_levels is None:
        config = COUNTRY_CONFIGS.get(country, {})
        district_levels = config.get("district_levels", ["7", "8"])

    # 1️⃣ Resolve city
    print(f"🌐 Resolving City: {city_query}, {country}...")
    locations = geolocator.geocode(f"{city_query}, {country}", exactly_one=False, limit=5)
    if not locations:
        print(f"❌ Could not resolve city: {city_query}, {country}")
        return None, None

    target_location = next((loc for loc in locations if loc.raw.get('osm_type') == 'relation'), locations[0])
    print(f"✅ Using Relation ID: {target_location.raw.get('osm_id')}")

    osm_id = int(target_location.raw.get('osm_id'))
    area_id = osm_id + 3600000000

    # 2️⃣ Try district_levels in order until GeoJSON is found
    for level in district_levels:
        try:
            print(f"🌍 Fetching Level {level} Districts for {city_query}...")
            query = f"""
            [out:json][timeout:180];
            area({area_id})->.cityArea;
            (relation["boundary"="administrative"]["admin_level"="{level}"](area.cityArea););
            out geom;
            """
            response = requests.get(overpass_url, params={'data': query}, timeout=180)
            response.raise_for_status()
            geojson_data = osm2geojson.json2geojson(response.json())

            if geojson_data.get("features"):
                return geojson_data, target_location
            else:
                print(f"⚠️ No features found at level {level} for {city_query}, trying next level...")
        except Exception as e:
            print(f"❌ Error fetching level {level}: {e}")
            continue

    print(f"❌ Failed to fetch GeoJSON for {city_query}, {country} at levels {district_levels}")
    return None, None

import json, folium, os, branca.colormap as cm

def create_base_map(center=[23.7, 121], zoom=7, interactive=True):
    """Creates a new Folium Map instance."""
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="cartodbpositron",
        dragging=interactive,
        touch_zoom=interactive,
        scroll_wheel_zoom=interactive,
        double_click_zoom=interactive,
        zoom_control=interactive
    )
    colormap = cm.LinearColormap(
        colors=["red", "orange", "yellow", "green"],
        vmin=0, vmax=1,
        caption="Score"
    )
    colormap.add_to(m)
    return m, colormap

def add_geojson_layer(map_object, colormap, city, topic, scores, is_visible=True, geo_file=""):
    """Adds a styled GeoJSON FeatureGroup layer to a Folium map."""
    layer_id = f"{city}_{topic}"

    if not os.path.exists(geo_file):
        print(f"Warning: GeoJSON file not found: {geo_file}")
        return

    with open(geo_file) as f:
        geojson_data = json.load(f)

    # Attach scores, district name, and a unique layer_id to each feature
    for feature in geojson_data["features"]:
        props = feature["properties"]
        district = (props.get("tags", {}).get("name:en") or
                    props.get("tags", {}).get("name") or
                    props.get("name") or
                    "Unnamed Area")
        feature["properties"]["district"] = district
        feature["properties"]["score"] = scores.get(district)
        feature["properties"]["layer_id"] = layer_id  # For multi-layer click handling

    # Style function uses the passed-in colormap
    def style_function(feature):
        score = feature["properties"].get("score")
        if score is None:
            return {"fillColor": "#ddd", "color": "black", "weight": 1, "fillOpacity": 0.4}
        return {"fillColor": colormap(score), "color": "black", "weight": 1, "fillOpacity": 0.75}

    # Create a toggleable FeatureGroup for the layer
    feature_group = folium.FeatureGroup(name=layer_id, show=is_visible)

    folium.GeoJson(
        geojson_data,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["district", "score", "layer_id"],
            aliases=["District:", "Score:", "Layer:"],
            localize=True
        ),
        highlight_function=lambda x: {"weight": 3, "color": "blue"}
    ).add_to(feature_group)

    # Add the layer to the main map
    feature_group.add_to(map_object)