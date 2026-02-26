# test_japan_subregions.py
import json
from geopy.geocoders import Nominatim
import requests
import osm2geojson

# COUNTRY_CONFIGS from your config file
COUNTRY_CONFIGS = {
    "Taiwan": {
        "city_admin_level": "6",   # immediate subareas (cities/counties)
        "district_levels": ["7", "8"],  # level 7 primary, fallback to 8
        "default_district_level": "7",
    },
    "Japan": {
        "city_admin_level": "4",   # prefectures or major cities
        "district_levels": ["7", "8"],  # prefectures → wards/districts
        "default_district_level": "7",
    },
}

def get_country_subareas(country_name):
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="country_subarea_test")

    config = COUNTRY_CONFIGS.get(country_name)
    print("config loaded")
    if not config:
        raise ValueError(f"No configuration found for country '{country_name}'")
    admin_level = config.get("city_admin_level", "4")

    # Resolve country
    locations = geolocator.geocode(country_name, exactly_one=False, limit=5)
    print(admin_level)
    if not locations:
        print(f"❌ Could not resolve country: {country_name}")
        return None, None

    target_location = next((loc for loc in locations if loc.raw.get("osm_type")=="relation"), locations[0])
    osm_id = int(target_location.raw.get("osm_id"))
    area_id = osm_id + 3600000000

    print("area_id", area_id)
    # Query subareas
    query = f"""
            [out:json][timeout:180];
            area({area_id})->.cityArea;
            (relation["boundary"="administrative"]["admin_level"="{admin_level}"](area.cityArea););
            out geom; 
            """
    print("query sent")
    response = requests.get(overpass_url, params={'data': query}, timeout=300)
    print("response received", response.json())
    response.raise_for_status()
    geojson_data = osm2geojson.json2geojson(response.json())
    return geojson_data

if __name__ == "__main__":
    print("Fetching Japan subregions...")
    geojson_japan = get_country_subareas("Japan")
    if geojson_japan and geojson_japan.get("features"):
        # Save to JSON
        with open("japan_subregions.json", "w", encoding="utf-8") as f:
            json.dump(geojson_japan, f, ensure_ascii=False, indent=2)
        print("✅ Saved Japan subregions to japan_subregions.json")
    else:
        print("❌ Failed to fetch Japan subregions")