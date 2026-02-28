# main.py
from country_configs import COUNTRY_CONFIGS
import json
import os
import requests
import dotenv
from langchain_openai import ChatOpenAI
from map_tool import get_city_geojson
from googletrans import Translator
from wikidata.client import Client
import wikipedia
from ddgs import DDGS

dotenv.load_dotenv()

# ────────────────────────────────────────────────
# Environment
# ────────────────────────────────────────────────
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not SERPER_API_KEY:
    raise ValueError("SERPER_API_KEY not set")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not set")

translator = Translator()

llm = ChatOpenAI(
    model="stepfun/step-3.5-flash:free",
    temperature=0,
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
)

TIME_FILTER = "113年 OR 114年 OR 2024 OR 2025"

# ────────────────────────────────────────────────
# Topic Config
# ────────────────────────────────────────────────

TOPIC_CONFIG = {
    "cleanliness": {'keywords':["cleanliness", "環境衛生", "垃圾清運", "整潔", "公共場所衛生"],},
    "air quality": {'keywords':["air quality", "空氣品質", "PM2.5", "AQI"],},
    "safety": {
        "keywords": (
            '"crime rate" OR '
            '"public safety" OR '
            '"police reports" OR '
            '"crime statistics" OR '
            '"safety index" OR '
            '"reported incidents"'
        )
    },
    "cost of living": {
        "keywords": (
            '"housing prices" OR '
            '"rent prices" OR '
            '"cost of living" OR '
            '"real estate market" OR '
            '"property prices" OR '
            '"living expenses"'
        )
    },
}
# ────────────────────────────────────────────────
# Search
# ────────────────────────────────────────────────
def duckduckgo_search(query, max_results=6):
    """
    Uses duckduckgo-search's DDGS class to fetch web search results.
    Returns a list of individual snippets for scoring.
    """
    snippets = []
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        for r in results:
            # Each result is a dict with title, url, snippet fields
            title = r.get("title", "")
            body  = r.get("body", "") or r.get("snippet", "")
            snippets.append(f"{title} - {body}")
    return snippets  # <-- return list, not joined string


def serper_search(query, max_results=6):
    """
    Uses Serper API to fetch Google search results.
    Returns a list of individual snippets for scoring.
    """
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": max_results})

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    results = response.json()

    snippets = []

    # Include answer box if present
    if "answerBox" in results and results["answerBox"].get("answer"):
        snippets.append(results["answerBox"]["answer"])

    for r in results.get("organic", [])[:max_results]:
        snippets.append(f"{r.get('title', '')} - {r.get('snippet', '')}")

    return snippets  # <-- return list, not joined string
# ────────────────────────────────────────────────
# GeoJSON Handling
# ────────────────────────────────────────────────
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

def build_extraction_prompt(topic, district, city, country, area_info):
    """
    Builds a topic-specific prompt for LLM extraction.
    Guarantees no null values; LLM should estimate if exact data is missing.
    Numeric values remain numeric; subjective metrics use 5-level descriptive scale.
    """
    base_instructions = f"""
You are an urban data analyst.
Extract measurable data from the following information for {district}, {city}, {country}.

DATA:
{area_info}

TASK:
Return ONLY a JSON object with the relevant fields for the topic "{topic}".
- All fields MUST have a value; if unknown, make a reasonable estimate based on context.
- Use descriptive 5-level scale for subjective metrics: "very poor", "poor", "average", "good", "excellent".
- Return exactly as JSON, no extra text.
"""

    if topic == "cleanliness":
        schema = """
{
    "street_cleanliness": "very poor" | "poor" | "average" | "good" | "excellent",
    "park_cleanliness": "very poor" | "poor" | "average" | "good" | "excellent",
    "waste_management_efficiency": "very poor" | "poor" | "average" | "good" | "excellent",
    "public_facility_sanitation": "very poor" | "poor" | "average" | "good" | "excellent",
    "citizen_feedback": "very poor" | "poor" | "average" | "good" | "excellent"
}
"""
    elif topic == "air quality":
        schema = """
{
    "aqi": 0-500,                             // numeric AQI, estimate if unknown
    "pm25": 0-500,                            // numeric PM2.5
    "air_quality_trend": "very poor" | "poor" | "average" | "good" | "excellent",
    "visibility": "very poor" | "poor" | "average" | "good" | "excellent",
    "citizen_feedback": "very poor" | "poor" | "average" | "good" | "excellent"
}
"""
    elif topic == "safety":
        schema = """
{
    "crime_rate": 0-100,                       // numeric incidents per 1000 people
    "police_presence": "very poor" | "poor" | "average" | "good" | "excellent",
    "traffic_safety": "very poor" | "poor" | "average" | "good" | "excellent",
    "emergency_response": "very poor" | "poor" | "average" | "good" | "excellent",
    "citizen_sense_of_safety": "very poor" | "poor" | "average" | "good" | "excellent"
}
"""
    elif topic == "cost of living":
        schema = """
{
    "median_rent": 0-5000,                     // numeric monthly rent
    "rent_affordability": "very poor" | "poor" | "average" | "good" | "excellent",
    "food_cost": "very poor" | "poor" | "average" | "good" | "excellent",
    "public_transport_cost": "very poor" | "poor" | "average" | "good" | "excellent",
    "overall_expenses": "very poor" | "poor" | "average" | "good" | "excellent"
}
"""
    else:
        schema = '{"note": "Unknown topic, return estimates for key metrics if possible"}'

    return base_instructions + "\n\nSCHEMA:\n" + schema

# ────────────────────────────────────────────────
# Signals → numeric score mapping
# ────────────────────────────────────────────────
DESCRIPTIVE_SCALE = {
    "very poor": 0.0,
    "poor": 0.25,
    "average": 0.5,
    "good": 0.75,
    "excellent": 1.0
}

def signals_to_score(topic, signals):
    """
    Converts extracted signals into a 0-1 numeric score.
    Numeric metrics are normalized; descriptive metrics use 5-level scale.
    """
    if not signals:
        return 0.5

    def map_signal(key):
        value = signals.get(key)
        if isinstance(value, str):
            return DESCRIPTIVE_SCALE.get(value.lower(), 0.5)
        elif isinstance(value, (int, float)):
            # normalize numeric fields to 0-1
            if key in ["aqi", "pm25"]:
                return 1 - min(value, 500)/500
            elif key in ["median_rent", "crime_rate"]:
                # assume max reasonable values
                max_val = 5000 if key == "median_rent" else 100
                return 1 - min(value, max_val)/max_val
            else:
                return 0.5
        return 0.5

    if topic == "cleanliness":
        metrics = [
            map_signal("street_cleanliness"),
            map_signal("park_cleanliness"),
            map_signal("waste_management_efficiency"),
            map_signal("public_facility_sanitation"),
            map_signal("citizen_feedback")
        ]
    elif topic == "air quality":
        metrics = [
            map_signal("aqi"),
            map_signal("pm25"),
            map_signal("air_quality_trend"),
            map_signal("visibility"),
            map_signal("citizen_feedback")
        ]
    elif topic == "safety":
        metrics = [
            map_signal("crime_rate"),
            map_signal("police_presence"),
            map_signal("traffic_safety"),
            map_signal("emergency_response"),
            map_signal("citizen_sense_of_safety")
        ]
    elif topic == "cost of living":
        metrics = [
            map_signal("median_rent"),
            map_signal("rent_affordability"),
            map_signal("food_cost"),
            map_signal("public_transport_cost"),
            map_signal("overall_expenses")
        ]
    else:
        metrics = [0.5]

    raw_score = sum(metrics)/len(metrics)
    return round(raw_score,2)

def generate_search_plan(topic, district, city, country, history):
    prompt = f"""
You are an autonomous research agent improving your search strategy.

Goal:
Find reliable, district-specific evidence about "{topic}"
in {district}, {city}, {country}.

Previous Attempts:
{json.dumps(history, indent=2)}

Analyze:
- Why did previous attempts fail?
- Were results city-wide instead of district-level?
- Were they outdated?
- Were they irrelevant domains?

Now propose a NEW strategy.

Rules:
- Do NOT repeat failed query patterns.
- If district specificity was weak, strengthen it.
- If English failed, try native language.
- If government sources failed, try statistical keywords.
- Be concrete and different.

Return ONLY JSON:
{{
  "strategy_reasoning": "short explanation",
  "queries": ["query1", "query2", "query3"]
}}
"""
    reply = llm.invoke(prompt).content.strip()

    try:
        data = json.loads(reply)
        print("🧠 Strategy:", data["strategy_reasoning"])
        return data["queries"]
    except:
        return []
def evaluate_retrieval(topic, district, city, country, results_text):
    prompt = f"""
You are evaluating search result quality.

Topic: {topic}
Location: {district}, {city}, {country}

Search Results:
{results_text}

Evaluate:
1. Are the results specific to the correct district?
2. Are they about the requested topic?
3. Are they recent and data-driven?

Provide structured feedback focused on **patterns the agent can learn from**:
- what_worked: abstract patterns to reinforce (e.g., district-specific content, official sources, statistical/data-driven reports, recent years)
- what_didnt_work: abstract patterns to avoid (e.g., wrong district, outdated content, irrelevant topics, non-official sources)

**IMPORTANT:** Return JSON ONLY, in this exact skeleton. Fill the lists with patterns/signals; do not leave fields out or add extra keys.

Example output:

{{
  "relevance_score": 0.0,
  "needs_refinement": true,
  "what_worked": [],
  "what_didnt_work": []
}}

Return your JSON below:
"""
    reply = llm.invoke(prompt).content.strip()
    try:
        return json.loads(reply)
    except Exception as e:
        print("Evaluation parsing failed:", e)
        return {
            "relevance_score": 0.0,
            "needs_refinement": True,
            "what_worked": [],
            "what_didnt_work": []
        }
    
import re
def evaluate_single_result(topic, district, city, country, text):
    text_lower = text.lower()
    score = 0.0

    keywords = TOPIC_CONFIG.get(topic, {"keywords":[topic]}).get("keywords", [])

    # ---- District mention ----
    if district.lower() in text_lower:
        score += 0.4  # strong signal

    # ---- Keyword/topic mentions ----
    for kw in keywords:
        if kw.lower() in text_lower:
            score += 0.2  # presence counts, not frequency

    # ---- Data/report signals ----
    data_keywords = ["統計", "數據", "報告", "年", "資料", "table", "statistics"]
    data_hits = sum(1 for k in data_keywords if k.lower() in text_lower)
    score += min(data_hits * 0.05, 0.15)

    # ---- Government source ----
    if ".gov" in text_lower or ".gov.tw" in text_lower:
        score += 0.1

    return min(score, 1.0)

def agentic_retrieval(district, city, country, topic, max_iters=3):
    best_results = ""
    best_score = 0.0

    iteration_history = []

    for i in range(max_iters):

        print(f"\n🧠 Agent iteration {i+1}")

        queries = generate_search_plan(
            topic, district, city, country,
            iteration_history
        )

        iteration_results = []
        for q in queries:
            print("🔎 Query:", q)

            try:
                serper_res = serper_search(q)
                if serper_res:
                    iteration_results.extend(serper_res)  # <-- merge all items
            except Exception as e:
                print("Serper search failed:", e)

            try:
                ddg_res = duckduckgo_search(q)
                if ddg_res:
                    iteration_results.extend(ddg_res)      # <-- merge all items
            except Exception as e:
                print("DuckDuckGo search failed:", e)

        # ---- STEP 1: Per-result scoring ----
        scored_results = []
        for idx, result in enumerate(iteration_results):
            score = evaluate_single_result(topic, district, city, country, result)
            if score > 0.0:
                print(f"Evaluated result {idx} of {len(iteration_results)}. Score: {score}")
                scored_results.append((result, score))
        # Sort by score descending
        scored_results.sort(key=lambda x: x[1], reverse=True)

        # Keep top N
        top_results = [r[0] for r in scored_results[:8]]
        print(f"Narrowed to {len(top_results)} search results")
        combined = "\n\n".join(top_results)

        # ---- STEP 2: Evaluate iteration quality ----
        evaluation = evaluate_retrieval(
            topic, district, city, country, combined
        )

        relevance_score = evaluation.get("relevance_score", 0.0)

        print("📊 Relevance:", evaluation)

        # Track best iteration
        if relevance_score > best_score:
            best_score = relevance_score
            best_results = combined

        iteration_history.append({
            "queries": queries,
            "evaluation": evaluation
        })

        if not evaluation.get("needs_refinement", True):
            print("✅ Agent satisfied with retrieval quality")
            break

    print(f"\n🏁 Best relevance achieved: {best_score}")
    return best_results

def score_district(data_file, city, country, topic, district, logger=print, force_refresh=False):
    """
    Scores ONE district and returns float.
    Uses cached value unless force_refresh=True.
    Now uses submetrics for more stable scoring.
    """
    if not force_refresh and os.path.exists(data_file):
        with open(data_file) as f:
            existing = json.load(f)
            if district in existing:
                logger("📂 Using cached score")
                return existing[district]
    else:
        existing = {}

    if force_refresh:
        logger("🔄 Force refresh enabled — fetching fresh data")
    logger(f"🔍 Searching data for {district}...")

    area_info = agentic_retrieval(district, city, country, topic)
    logger("🤖 Running LLM scoring...")
    extraction_prompt = build_extraction_prompt(topic, district, city, country, area_info)
    reply = llm.invoke(extraction_prompt).content.strip()
    print(district, city, country, ":\n", reply)
    try:
        signals = json.loads(reply)
    except:
        signals = {}

    score = signals_to_score(topic, signals)
    logger(f"✅ Score: {score:.2f}")

    # Save cache
    existing[district] = score
    with open(data_file, "w") as f:
        json.dump(existing, f, indent=4)

    return score