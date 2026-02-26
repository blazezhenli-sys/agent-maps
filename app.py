# app.py
import streamlit as st
import os
import json
from streamlit_folium import st_folium
from map_tool import generate_interactive_map
from main import ensure_geojson, score_district

st.set_page_config(layout="wide")
st.title("Taiwan District Agent Maps")

# ─────────────────────────────────────
# Session State Defaults
# ─────────────────────────────────────
if "scores" not in st.session_state:
    st.session_state.scores = {}

if "selected_city" not in st.session_state:
    st.session_state.selected_city = None  # Start with no city selected

if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = "cleanliness"

if "map_center" not in st.session_state:
    st.session_state.map_center = [23.7, 121]

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 7

if "district_to_process" not in st.session_state:
    st.session_state.district_to_process = None

# ─────────────────────────────────────
# AI Processing Block
# ─────────────────────────────────────
if st.session_state.district_to_process:
    district = st.session_state.district_to_process
    with st.spinner(f"Running AI for {district}..."):
        try:
            score = score_district(
                city=st.session_state.selected_city,
                topic=st.session_state.selected_topic,
                district=district,
                logger=lambda x: st.write(x)
            )
            st.session_state.scores[district] = score
            st.success(f"{district} scored: {score:.2f}")

            # Save updated scores
            with open(f"{st.session_state.selected_city}_{st.session_state.selected_topic}_data.json", "w") as f:
                json.dump(st.session_state.scores, f, indent=2)

        except Exception as e:
            st.error(f"AI failed: {e}")
        
        finally:
            # Always clear the processing state and rerun
            st.session_state.district_to_process = None
            st.rerun()

# ─────────────────────────────────────
# Sidebar Inputs
# ─────────────────────────────────────
city_input = st.sidebar.text_input("City", "Taipei, Taiwan")
topic_input = st.sidebar.selectbox(
    "Metric",
    ["cleanliness", "air quality", "safety", "cost of living"],
    index=["cleanliness", "air quality", "safety", "cost of living"].index(st.session_state.selected_topic)
)
load_map = st.sidebar.button("Load Map")

# ─────────────────────────────────────
# Map Loading Logic
# ─────────────────────────────────────
if load_map:
    st.session_state.selected_city = city_input
    st.session_state.selected_topic = topic_input
    st.session_state.scores = {}  # Reset scores for new selection

    # Load cached scores
    score_file = f"{st.session_state.selected_city}_{st.session_state.selected_topic}_data.json"
    if os.path.exists(score_file):
        with open(score_file) as f:
            st.session_state.scores = json.load(f)

    # Ensure GeoJSON exists before proceeding to render
    try:
        ensure_geojson(st.session_state.selected_city, st.session_state.selected_topic)
    except Exception as e:
        st.error(f"Failed to load boundaries for '{st.session_state.selected_city}': {e}")
        st.info("This can happen if the city name is not found or if there's an issue with the mapping services. Please try a different city, or check the name for typos.")
        st.session_state.selected_city = None # Reset city to prevent rendering a broken map
        st.stop()

# ─────────────────────────────────────
# Main View: Map or Initial Message
# ─────────────────────────────────────
if st.session_state.selected_city:
    # Render map and associated UI only if a city has been successfully loaded
    base_map = generate_interactive_map(
        city=st.session_state.selected_city,
        topic=st.session_state.selected_topic,
        scores=st.session_state.scores,
        map_center=st.session_state.map_center,
        map_zoom=st.session_state.map_zoom,
        interactive=(st.session_state.district_to_process is None)
    )

    map_data = None
    if base_map:
        map_data = st_folium(
            base_map,
            width=1000,
            height=700,
            key=f"{st.session_state.selected_city}_{st.session_state.selected_topic}_map"
        )

    # Detect Clicked District & Run AI
    if map_data and map_data.get("last_active_drawing"):
        if "center" in map_data:
            st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
        if "zoom" in map_data:
            st.session_state.map_zoom = map_data["zoom"]

        props = map_data["last_active_drawing"]["properties"]
        district = props.get("district")
        if district:
            if district in st.session_state.scores:
                st.info(f"{district} already scored: {st.session_state.scores[district]:.2f}")
            else:
                st.session_state.district_to_process = district
                st.rerun()

    # Sidebar Rankings
    if st.session_state.scores:
        st.sidebar.markdown("### Ranked Districts")
        sorted_scores = sorted(
            st.session_state.scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        for i, (district, score) in enumerate(sorted_scores, 1):
            st.sidebar.write(f"{i}. {district} — {score:.2f}")

else:
    # Initial view before any map is loaded
    st.info("Please enter a city and click 'Load Map' to begin.")