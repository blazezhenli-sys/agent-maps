import json
from main import save_geojson, save_mappings
import random
from map_tool import get_city_geojson, generate_choropleth

def test_map_visualization(city_query, topic):
    print(f"🚀 Fast-Testing Map UI for {city_query}...")
    
    # 1. Fetch the real shapes (Only happens once, uses cache if you have it)
    jsonTuple = get_city_geojson(city_query)
    save_geojson(jsonTuple[0], city_query, topic)

    geojson_data, location = jsonTuple
    print(geojson_data)
    
    if not geojson_data:
        print("❌ Failed to fetch shapes.")
        return

    # 2. MOCK THE RESEARCH DATA
    # Instead of asking an LLM, we just assign random scores to the official names
    mock_results = []
    
    # Standard GeoJSON path: features -> properties -> name
    for feature in geojson_data['features']:
        name = feature['properties'].get('tags').get('name:en')
        if name:
            # Generate a random "Cleanliness" score
            mock_results.append({
                "name": name, 
                "value": round(random.uniform(0.1, 0.9), 2)
            })

    print(f"📊 Generated mock data for {len(mock_results)} districts.")

    # 3. GENERATE THE MAP
    # Ensure your generate_choropleth is updated to accept (city, data_list, geojson, location)
    data_map = {item['name']: item['value'] for item in mock_results}
    save_mappings(data_map, city_query, topic)
    status = generate_choropleth(city_query, data_map, jsonTuple, topic)
    print(status)

if __name__ == "__main__":
    # Test for Taichung City, Taiwan
    test_map_visualization("New Taipei City, Taiwan", "cleanliness")
