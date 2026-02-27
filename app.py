# app.py
import streamlit as st
import os
import json
import folium
from streamlit_folium import st_folium
from map_tool import create_base_map, add_geojson_layer, get_country_subareas
from main import ensure_geojson, score_district
from country_configs import COUNTRY_CONFIGS

# ─────────────────────────────────────
st.set_page_config(layout="wide")
# ─────────────────────────────────────
# Session State Defaults for Multi-Layer Maps
# ─────────────────────────────────────
if "map_layers" not in st.session_state:
    st.session_state.map_layers = {}
if "selected_country" not in st.session_state:
    st.session_state.selected_country = "Taiwan"
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = "cleanliness"
if "force_refresh" not in st.session_state:
    st.session_state.force_refresh = False
# Initialize map position once
if "map_center" not in st.session_state:
    config = COUNTRY_CONFIGS.get(st.session_state.selected_country, {})
    st.session_state.map_center = config.get("map_center", [23.7, 121])
    st.session_state.map_zoom = config.get("map_zoom", 7)

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
        city, topic, country = layer["city"], layer["topic"], layer["country"]
        with st.spinner(f"Running AI for {district} ({topic})..."):
            try:
                score_file = st.session_state.map_layers[layer_id]["score_file"]
                score = score_district(data_file=score_file, city=city, country=country, topic=topic, district=district, logger=st.write, force_refresh=st.session_state.force_refresh)
                st.session_state.map_layers[layer_id]["scores"][district] = score
                st.success(f"{district} ({topic}) scored: {score:.2f}")

                # Save updated scores for the specific layer
                with open(score_file, "w") as f:
                    json.dump(st.session_state.map_layers[layer_id]["scores"], f, indent=2)

            except Exception as e:
                st.error(f"AI failed for {district}: {e}")
            finally:
                st.session_state.district_to_process = None
                st.session_state.layer_to_process = None
                st.rerun()

# ─────────────────────────────────────
# Main View: Map Rendering
# ─────────────────────────────────────
m, colormap= create_base_map(st.session_state.map_center, st.session_state.map_zoom, (st.session_state.district_to_process is None))
if not st.session_state.map_layers:
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
                geo_file=layer_data["geo_file"],
            )
    
    folium.LayerControl().add_to(m)
    map_data = st_folium(m, width=1200, height=800, key="map_output_layers")



# ─────────────────────────────────────
# Sidebar UI with Country Dropdown
# ─────────────────────────────────────

# Country dropdown (currently only Taiwan)
country_input = st.sidebar.selectbox(
    "Country",
    list(COUNTRY_CONFIGS.keys()),
    index=list(COUNTRY_CONFIGS.keys()).index(st.session_state.selected_country)
)

if country_input != st.session_state.selected_country:
    st.session_state.selected_country = country_input

    country_config = COUNTRY_CONFIGS.get(country_input, {})

    # Move map to new country default
    st.session_state.map_center = country_config.get("map_center", [23.7, 121])
    st.session_state.map_zoom = country_config.get("map_zoom", 7)

    # Optional but recommended: clear old layers
    st.session_state.map_layers = {}

    st.rerun()

# Cache file path now uses country variable
CACHE_FILE = f"countries/{country_input.lower()}/cities.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

if os.path.exists(CACHE_FILE):
    # Load cached cities
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        country_cities = json.load(f)
else:
    # Fetch from OSM and save
    geojson_country, _ = get_country_subareas(country_input)
    if geojson_country and geojson_country.get("features"):
        # Use English names if available
        country_cities = [f["properties"]['tags'].get("name:en", f["properties"]['tags'].get("name")) 
                          for f in geojson_country["features"]]
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(country_cities, f, ensure_ascii=False, indent=2)
        print(f"✅ Fetched {country_input} cities from OSM and cached locally.")
    else:
        country_cities = ["Hsinchu County"]  # fallback
        print(f"⚠️ Failed to fetch {country_input} cities. Using fallback list.")

# City dropdown uses the loaded cities
city_input = st.sidebar.selectbox("City / County", country_cities)

# Metric dropdown
topic_input = st.sidebar.selectbox(
    "Metric",
    ["cleanliness", "air quality", "safety", "cost of living"],
    index=["cleanliness", "air quality", "safety", "cost of living"].index(st.session_state.selected_topic)
)
st.session_state.force_refresh = st.sidebar.checkbox(
    "Force refresh (ignore cached scores)",
    value=st.session_state.force_refresh
)
if topic_input != st.session_state.selected_topic:
    st.session_state.selected_topic = topic_input
    st.session_state.map_layers = {}  
    st.session_state.district_to_process = None
    st.session_state.layer_to_process = None
    st.rerun()

if st.sidebar.button("Add Map Layer"):
    # Save current viewport from the rendered map
    if map_data and "center" in map_data and "zoom" in map_data:
        st.session_state.map_center = [
            map_data["center"]["lat"],
            map_data["center"]["lng"]
        ]
        st.session_state.map_zoom = map_data["zoom"]

    layer_id = f"{city_input}_{topic_input}"

    geo_file, score_file = ensure_geojson(city_input, topic_input, country=country_input)
    scores = {}
    if os.path.exists(score_file):
        with open(score_file, "r", encoding="utf-8") as f:
            scores = json.load(f)

    st.session_state.map_layers[layer_id] = {
        "city": city_input,
        "country": country_input,
        "topic": topic_input,
        "scores": scores,
        "is_visible": True,
        "geo_file": geo_file,
        "score_file": score_file,
    }

    st.rerun()

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
        if district in layer_scores and not st.session_state.force_refresh:
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