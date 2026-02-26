import requests
import json
import osm2geojson
from geopy.geocoders import Nominatim

def test_osm_id_search(city_query):
    url = "https://overpass.kumi.systems/api/interpreter"
    geolocator = Nominatim(user_agent="blaze_map_tester_v1")
    
    # 1. SEARCH FOR ALL MATCHES (Not just exactly_one)
    print(f"🌐 Step 1: Searching for {city_query} boundaries...")
    locations = geolocator.geocode(city_query, exactly_one=False, limit=5)
    
    if not locations:
        print("❌ Could not find that city.")
        return

    # 2. FIND THE RELATION IN THE LIST
    target_location = None
    for loc in locations:
        if loc.raw.get('osm_type') == 'relation':
            target_location = loc
            break
    
    # If no relation found, default to the first result (Node)
    if not target_location:
        target_location = locations[0]
        print(f"⚠️ No relation found. Using {target_location.raw.get('osm_type')}")
    else:
        print(f"✅ Found Relation ID: {target_location.raw.get('osm_id')}")

    # 3. AREA ID MATH
    osm_id = int(target_location.raw.get('osm_id'))
    osm_type = target_location.raw.get('osm_type')
    
    if osm_type == 'relation':
        area_selector = f"area({osm_id + 3600000000})"
    else:
        # Fallback to name search if we still only have a node
        area_selector = f'area[name="{city_query.split(",")[0]}"]'

    # In your Query string:
    # Use the area_id we found (111968 + 3600000000)
    query = f"""
    [out:json][timeout:180];
    area({osm_id + 3600000000})->.cityArea;
    (
    // Strictly only Level 7 (Districts)
    relation["boundary"="administrative"]["admin_level"="7"](area.cityArea);
    );
    out geom; 
    """




    print(f"📡 Step 2: Fetching shapes from {url}...")
    try:
        response = requests.get(url, params={'data': query}, timeout=40)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            osm_data = response.json()
            
            # Convert to standard GeoJSON
            geojson_data = osm2geojson.json2geojson(osm_data)
            
            # Extract names to verify we are in the right city
            names = [f.get('properties', {}).get('name') for f in geojson_data.get('features', [])]
            names = [n for n in names if n] # Filter out None
            
            # Save to file
            filename = "city_shapes_id_test.geojson"
            with open(filename, "w") as f:
                json.dump(geojson_data, f, indent=4)
            
            print(f"✅ Success! Saved {len(geojson_data['features'])} features to {filename}")
            print(f"📍 Sample Neighborhoods Found: {', '.join(names[:5])}...")
        else:
            print(f"❌ Server Error: {response.text}")
            
    except Exception as e:
        print(f"💥 Failed: {e}")

if __name__ == "__main__":
    # Test with the specific string to ensure it hits California
    test_osm_id_search("New Taipei City, Taiwan")
