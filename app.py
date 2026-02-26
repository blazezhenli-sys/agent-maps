# app.py
import streamlit as st
import os
import json
import folium
from streamlit_folium import st_folium
from map_tool import create_base_map, add_geojson_layer, get_country_subareas
from main import ensure_geojson, score_district

st.set_page_config(layout="wide")
st.title("Taiwan District Agent Maps")

# ─────────────────────────────────────
# Session State Defaults for Multi-Layer Maps
# ─────────────────────────────────────
if "map_layers" not in st.session_state:
    st.session_state.map_layers = {}

if "map_center" not in st.session_state:
    st.session_state.map_center = [23.7, 121]

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 7

# State for triggering AI runs
if "district_to_process" not in st.session_state:
    st.session_state.district_to_process = None
if "layer_to_process" not in st.session_state:
    st.session_state.layer_to_process = None

# ─────────────────────────────────────
# Layer-Aware AI Processing Block
# ─────────────────────────────────────
if st.session_state.district_to_process and st.session_state.layer_to_process:
    layer_id = st.session_state.layer_to_process
    district = st.session_state.district_to_process
    
    if layer_id in st.session_state.map_layers:
        layer = st.session_state.map_layers[layer_id]
        city, topic = layer["city"], layer["topic"]

        with st.spinner(f"Running AI for {district} ({topic})..."):
            try:
                score = score_district(city=city, topic=topic, district=district, logger=st.write)
                st.session_state.map_layers[layer_id]["scores"][district] = score
                st.success(f"{district} ({topic}) scored: {score:.2f}")

                # Save updated scores for the specific layer
                score_file = f"{city}_{topic}_data.json"
                with open(score_file, "w") as f:
                    json.dump(st.session_state.map_layers[layer_id]["scores"], f, indent=2)

            except Exception as e:
                st.error(f"AI failed for {district}: {e}")
            finally:
                st.session_state.district_to_process = None
                st.session_state.layer_to_process = None
                st.rerun()
# ─────────────────────────────────────
# Sidebar UI
# ─────────────────────────────────────

CACHE_FILE = "countries/taiwan/cities.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

if os.path.exists(CACHE_FILE):
    # 1️⃣ Load cached cities
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        taiwan_cities = json.load(f)
    print("✅ Loaded Taiwan cities from local cache.")
else:
    # 2️⃣ Fetch from OSM and save
    geojson_taiwan, _ = get_country_subareas("Taiwan", admin_level="4")
    if geojson_taiwan and geojson_taiwan.get("features"):
        taiwan_cities = [f["properties"]['tags']["name:en"] for f in geojson_taiwan["features"]]
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(taiwan_cities, f, ensure_ascii=False, indent=2)
        print("✅ Fetched Taiwan cities from OSM and cached locally.")
    else:
        # Fallback if fetching fails
        taiwan_cities = ["Hsinchu County"]
        print("⚠️ Failed to fetch Taiwan cities. Using fallback list.")

# Replace the text input with a dropdown
city_input = st.sidebar.selectbox("City / County", taiwan_cities)
topic_input = st.sidebar.selectbox("Metric", ["cleanliness", "air quality", "safety", "cost of living"])

if st.sidebar.button("Add Map Layer"):
    full_city_name = f"{city_input}, Taiwan"  # append country
    layer_id = f"{city_input}_{topic_input}"
    
    if layer_id not in st.session_state.map_layers:
        try:
            with st.spinner(f"Loading boundaries for {full_city_name}..."):
                # send full name to ensure_geojson
                ensure_geojson(full_city_name, topic_input)
            
            scores = {}
            score_file = f"{full_city_name}_{topic_input}_data.json"
            if os.path.exists(score_file):
                print("Found Saved Files")
                with open(score_file) as f: scores = json.load(f)
            
            st.session_state.map_layers[layer_id] = {
                "city": full_city_name,  # store full name for later consistency
                "topic": topic_input,
                "scores": scores,
                "is_visible": True,
            }
            st.rerun()
        except Exception as e:
            st.error(f"Failed to load layer for '{full_city_name}': {e}")
    else:
        st.warning(f"Layer '{layer_id}' is already loaded.")
# ─────────────────────────────────────
# Main View: Map Rendering
# ─────────────────────────────────────
m, colormap= create_base_map(st.session_state.map_center, st.session_state.map_zoom, (st.session_state.district_to_process is None))

if not st.session_state.map_layers:
    st.info("Add a map layer from the sidebar to begin.")
    map_data = st_folium(m, width=1200, height=800, key="map_output_initial")
else:
    for layer_id, layer_data in st.session_state.map_layers.items():
        # Robustly check if the item is a valid layer dictionary
        if isinstance(layer_data, dict) and "city" in layer_data:
            add_geojson_layer(
                map_object=m,
                colormap=colormap,
                city=layer_data["city"],
                topic=layer_data["topic"],
                scores=layer_data["scores"],
                is_visible=layer_data["is_visible"],
            )
    
    folium.LayerControl().add_to(m)
    map_data = st_folium(m, width=1200, height=800, key="map_output_layers")

# ─────────────────────────────────────
# Multi-Layer Click Handling
# ─────────────────────────────────────
if map_data and map_data.get("last_active_drawing"):
    st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
    st.session_state.map_zoom = map_data["zoom"]

    props = map_data["last_active_drawing"]["properties"]
    district, layer_id = props.get("district"), props.get("layer_id")

    if district and layer_id and layer_id in st.session_state.map_layers:
        layer_scores = st.session_state.map_layers[layer_id]["scores"]
        if district in layer_scores:
            st.info(f"{district} ({st.session_state.map_layers[layer_id]['topic']}) already scored: {layer_scores[district]:.2f}")
        else:
            st.session_state.district_to_process = district
            st.session_state.layer_to_process = layer_id
            st.rerun()

# ─────────────────────────────────────
# Sidebar Rankings per Layer
# ─────────────────────────────────────
if st.session_state.map_layers:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Ranked Districts")
    for layer_id, layer_data in st.session_state.map_layers.items():
        if isinstance(layer_data, dict) and layer_data.get("scores"):
            st.sidebar.markdown(f"**{layer_id}**")
            sorted_scores = sorted(layer_data["scores"].items(), key=lambda x: x[1], reverse=True)
            for i, (district, score) in enumerate(sorted_scores[:10], 1):
                st.sidebar.write(f"{i}. {district} — {score:.2f}")