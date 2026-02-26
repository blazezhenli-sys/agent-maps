# app.py
import streamlit as st
import os
import json
import pandas as pd
from map_tool import generate_choropleth
from main import run_pipeline_agent

st.set_page_config(page_title="Taiwan District Vibe Maps", layout="wide")
st.title("Taiwan District Agent Maps")

def make_logger(container, buffer):
    """
    Returns a logger function that appends to buffer and updates Streamlit container.
    """
    def logger(line):
        buffer.append(line)
        container.text("\n".join(buffer))
    return logger

# Example usage inside the main loop
topic_log = []
topic_status = st.empty()
logger = make_logger(topic_status, topic_log)

# ─────────────────────────────────────
# Sidebar inputs
# ─────────────────────────────────────
cities_input = st.sidebar.text_area(
    "Cities (one per line)", 
    value="Taichung, Taiwan\nTaipei, Taiwan",
    height=120
)
cities = [c.strip() for c in cities_input.split("\n") if c.strip()]

topics = st.sidebar.multiselect(
    "Select metrics to compare",
    options=["cleanliness", "air quality", "safety", "cost of living"],
    default=["cleanliness"]
)

regenerate = st.sidebar.checkbox("Force regenerate (ignore cached data)", value=False)
generate_button = st.sidebar.button("Generate Maps", type="primary")

# ─────────────────────────────────────
# Main execution
# ─────────────────────────────────────
if generate_button:

    if not topics or not cities:
        st.warning("Please enter at least one city and select at least one topic.")
    else:
        # Containers for logging
        status_container = st.empty()
        progress_bar = st.progress(0)

        # To store folium maps per topic
        maps = {}

        # Loop over topics
        for t_idx, topic in enumerate(topics):
            topic_log = ""  # buffer for topic-specific logs
            topic_status = st.empty()
            topic_log += f"=== Processing topic '{topic}' ===\n"
            topic_status.text(topic_log)

            # Run/load data for each city
            for c_idx, city in enumerate(cities):
                data_file = f"{city}_{topic}_data.json"
                geo_file = f"{city}_{topic}_map.geojson"

                if regenerate or not (os.path.exists(data_file) and os.path.exists(geo_file)):
                    topic_log += f"Running agent for {city}...\n"
                    topic_status.text(topic_log)

                    # Run agent; it saves JSON and GeoJSON
                    try:
                        run_pipeline_agent(city, topic, logger)
                        topic_log += f"✅ Agent completed for {city}\n"
                    except Exception as e:
                        topic_log += f"❌ Agent failed for {city}: {e}\n"
                        topic_status.text(topic_log)
                        continue
                else:
                    topic_log += f"Loading cached data for {city}...\n"
                    topic_status.text(topic_log)

            # ─────────────────────────────────────
            # Generate choropleth for this topic
            # ─────────────────────────────────────
            try:
                folium_map = generate_choropleth(cities, topic)
                if folium_map:
                    maps[topic] = folium_map
                    topic_log += f"🌐 Map generated for topic '{topic}'\n"
                else:
                    topic_log += f"⚠️ Map generation skipped for topic '{topic}'\n"
            except Exception as e:
                topic_log += f"❌ Map generation failed: {e}\n"

            topic_status.text(topic_log)
            progress_bar.progress((t_idx + 1) / len(topics))

        status_container.text("All topics processed ✅")

        # ─────────────────────────────────────
        # Display maps in tabs
        # ─────────────────────────────────────
        if maps:
            tab_list = st.tabs(list(maps.keys()))
            for tab, topic in zip(tab_list, maps.keys()):
                with tab:
                    st.subheader(topic.capitalize())
                    st.components.v1.html(
                        maps[topic]._repr_html_(),
                        height=700,
                        scrolling=True
                    )
        else:
            st.info("No maps were generated.")