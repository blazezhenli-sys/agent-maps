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

# def build_catalog_index(path="countries/taiwan/catalog/catalog.json"):
#     with open(path, "r", encoding="utf-8") as f:
#         raw = json.load(f)

#     records = raw["Records"]

#     index = []

#     for r in records:
#         index.append({
#             "title": r.get("資料集名稱", ""),
#             "desc": r.get("資料集描述", ""),
#             "columns": r.get("主要欄位說明", ""),
#             "category": r.get("服務分類", ""),
#             "format": r.get("檔案格式", ""),
#             "url": r.get("下載連結", "")
#         })

#     return index

# catalogue = build_catalog_index()

# def search_datasets(index, district_zh, city_zh, topic_zh, fuzzy_threshold=80):
#     """
#     Search datasets with:
#     - Mandatory district (fuzzy)
#     - Weighted scoring for district, city, topic (fuzzy)
#     - Deduplicate keeping the most recent dataset per title
#     """

#     def normalize_text(text):
#         import unicodedata, re
#         if not text:
#             return ""
#         text = unicodedata.normalize("NFKC", text)
#         text = text.lower()
#         text = re.sub(r'\s+', '', text)
#         return text

#     def fuzzy_score(text, term, weight, threshold=fuzzy_threshold):
#         """Return weighted score if fuzzy match exceeds threshold"""
#         if fuzz.partial_ratio(term, text) >= threshold:
#             return weight
#         return 0

#     def extract_year_from_title(title):
#         # Try Taiwanese calendar (e.g., 104年度) or 4-digit year
#         match = re.search(r"\((\d{3,4})年度\)", title)
#         if match:
#             return int(match.group(1))
#         match = re.search(r"\b(20\d{2})\b", title)
#         if match:
#             return int(match.group(1))
#         return 0

#     def deduplicate_keep_most_recent(matches):
#         # Sort by year descending
#         matches_sorted = sorted(matches, key=lambda ds: extract_year_from_title(ds["title"]), reverse=True)
#         seen_titles = set()
#         unique_matches = []
#         for ds in matches_sorted:
#             title = ds["title"]
#             if title not in seen_titles:
#                 unique_matches.append(ds)
#                 seen_titles.add(title)
#         return unique_matches

#     matches = []

#     district_norm = normalize_text(district_zh)
#     city_norm = normalize_text(city_zh)
#     topic_norm = normalize_text(topic_zh)

#     for ds in index:
#         title_norm = normalize_text(ds['title'])
#         desc_norm = normalize_text(ds['desc'])
#         columns_norm = normalize_text(ds['columns'])

#         # Require at least one district mention (fuzzy)
#         district_match = (
#             fuzz.partial_ratio(district_norm, title_norm) >= fuzzy_threshold or
#             fuzz.partial_ratio(district_norm, desc_norm) >= fuzzy_threshold or
#             fuzz.partial_ratio(district_norm, columns_norm) >= fuzzy_threshold
#         )
#         if not district_match:
#             continue

#         # Weighted fuzzy scoring
#         score = 0
#         score += fuzzy_score(title_norm, district_norm, 10)
#         score += fuzzy_score(desc_norm, district_norm, 5)
#         score += fuzzy_score(columns_norm, district_norm, 3)

#         score += fuzzy_score(title_norm, city_norm, 5)
#         score += fuzzy_score(desc_norm, city_norm, 2)

#         score += fuzzy_score(title_norm, topic_norm, 3)
#         score += fuzzy_score(desc_norm, topic_norm, 2)
#         score += fuzzy_score(columns_norm, topic_norm, 1)

#         ds_copy = ds.copy()
#         ds_copy["match_score"] = score
#         matches.append(ds_copy)

#     # Sort by score descending
#     matches.sort(key=lambda x: x["match_score"], reverse=True)
#     # Deduplicate keeping most recent dataset per title
#     matches = deduplicate_keep_most_recent(matches)

#     return matches

# def query_local_open_data(district, city, topic, max_results=5):
#     """
#     Searches local Taiwan open data catalog (already loaded into memory),
#     downloads matching dataset files (if JSON/CSV),
#     and returns concatenated data text for LLM context.
#     """
#     topic_map = {
#         "cleanliness": "清潔",
#         "air quality": "空氣品質",
#         "safety": "安全",
#         "cost of living": "生活成本"
#     }
#     # Translate to Traditional Chinese for Taiwan catalog matching
#     topic_zh = topic_map.get(topic.lower(), topic)
#     district_zh = translator.translate(district, dest="zh-tw").text

#     # Optionally normalize by stripping the "區" suffix
#     if district_zh.endswith("區"):
#         district_zh = district_zh[:-1]
#     city_zh = translator.translate(city, dest="zh-tw").text

#     matches = search_datasets(catalogue, district_zh, city_zh, topic_zh)
#     print(f"Found {len(matches)} matching datasets:")
#     for ds in matches:
#         print("-", ds["title"])
#     if not matches:
#         print("No Matches found in Datasets")
#         return ""
#     collected_text = []
#     download_count = 0

#     for ds in matches[:max_results]:
#         url = ds.get("url")
#         fmt = ds.get("format", "").lower()

#         if not url:
#             continue

#         try:
#             r = requests.get(url, timeout=15)
#             r.raise_for_status()

#             # Only process JSON or CSV
#             if "json" in fmt:
#                 data = r.json()
#                 collected_text.append(json.dumps(data)[:5000])  # truncate
#                 download_count += 1

#             elif "csv" in fmt:
#                 collected_text.append(r.text[:5000])  # truncate
#                 download_count += 1

#         except Exception:
#             continue

#     return "\n\n".join(collected_text)

# ────────────────────────────────────────────────
# Search
# ────────────────────────────────────────────────

def duckduckgo_search(query, max_results=6):
    """
    Uses duckduckgo-search's DDGS class to fetch web search results.
    """
    snippets = []
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        for r in results:
            # Each result is a dict with title, url, snippet fields
            title = r.get("title", "")
            body  = r.get("body", "") or r.get("snippet", "")
            snippets.append(f"{title} - {body}")
    return "\n\n".join(snippets)

def serper_search(query):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": 8})

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    results = response.json()

    parts = []

    if "answerBox" in results:
        parts.append(results["answerBox"].get("answer", ""))

    for r in results.get("organic", [])[:6]:
        parts.append(f"{r.get('title', '')} - {r.get('snippet', '')}")

    return "\n\n".join(parts)

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


def query_wikipedia(district, city, country):
    """
    Fetches enriched Wikipedia info for a district.
    Includes summary + sections like history, demographics, government.
    Safely skips missing sections.
    """
    wiki_summary = ""
    enriched_sections = {}
    page = None
    try:
        search_results = wikipedia.search(district)
        page_title = None
        for r in search_results:
            if district.lower() in r.lower():
                page_title = r
                break

        if page_title:
            page = wikipedia.page(page_title)


    except wikipedia.DisambiguationError as e:
        try:
            page = wikipedia.page(e.options[0])
        except:
            pass

    # Combine into area_info string
    area_info = f"Content: {page.content}\n\n"
    for sec, body in enriched_sections.items():
        area_info += f"{sec.capitalize()}:\n{body}\n\n"

    return area_info.strip()

def build_area_info(district, city, country, topic):
    """
    Builds a string of context for the LLM:
    - Wikipedia summary of the district
    - Web search snippets via Serper using topic keywords
    """
    area_info_parts = []

    # 1️⃣ Wikipedia facts
    try:
        wiki_facts = query_wikipedia(district, city, country)
        area_info_parts.append("Wikipedia Info:\n" + wiki_facts)
    except Exception as e:
        area_info_parts.append(f"Wikipedia Info: Failed to fetch ({e})")

    # 2️⃣ Web search facts (Serper)
    try:
        # Build query using TOPIC_CONFIG keywords
        keywords = TOPIC_CONFIG.get(topic, {}).get("keywords", "")
        search_query = f"{district} {city} ({keywords}) {TIME_FILTER}"
        web_facts = serper_search(search_query)
        if web_facts.strip():
            area_info_parts.append("Web Search Info:\n" + web_facts)
    except Exception as e:
        area_info_parts.append(f"Web Search Info: Failed to fetch ({e})")

    try:
        print("DDGS query:",search_query)
        ddg_facts = duckduckgo_search(search_query, max_results=6)
        if ddg_facts.strip():
            print("DuckDuckGo Info:\n" + ddg_facts)
            area_info_parts.append("DuckDuckGo Info:\n" + ddg_facts)
    except Exception as e:
        area_info_parts.append(f"DuckDuckGo Info: Failed ({e})")


    # Combine parts and truncate to LLM token limit
    area_info = "\n\n".join(area_info_parts)
    return area_info[:12000]  # truncate for safety
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

    area_info = build_area_info(district, city, country, topic)
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

TOPIC_CONFIG = {
    "cleanliness": {
        "keywords": (
            '"sanitation" OR '
            '"waste management" OR '
            '"recycling rate" OR '
            '"cleanliness ranking" OR '
            '"environmental hygiene" OR '
            '"garbage collection" OR '
            '"public cleanliness" OR '
            '"waste performance"'
        )
    },
    "air quality": {
        "keywords": (
            '"air quality" OR '
            '"PM2.5" OR '
            '"AQI" OR '
            '"air pollution" OR '
            '"air monitoring station" OR '
            '"pollution level" OR '
            '"smog"'
        )
    },
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