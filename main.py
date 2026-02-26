import re
import json
import os
import requests
from langchain_openai import ChatOpenAI
from map_tool import generate_choropleth, get_city_geojson
from googletrans import Translator
import dotenv

dotenv.load_dotenv()

# ────────────────────────────────────────────────
#  Environment & Globals
# ────────────────────────────────────────────────
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
if not SERPER_API_KEY:
    raise ValueError("SERPER_API_KEY environment variable not set")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set")

translator = Translator()

def serper_search(query):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": 12})
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
    for r in results.get("organic", [])[:10]:
        parts.append(f"{r.get('title', '')} - {r.get('snippet', '')}")
    return "\n\n".join(parts)

llm = ChatOpenAI(
    model="stepfun/step-3.5-flash:free",
    temperature=0,
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://your-app-domain.com",
        "X-Title": "Agent Maps",
    }
)

# ────────────────────────────────────────────────
#  Topic-specific configuration
# ────────────────────────────────────────────────

TOPIC_CONFIG = {
    "cleanliness": {
        "keywords": "清潔隊 OR 資源回收率 OR 回收考核 OR 評比成績 OR 排名 OR 績效 OR 乾淨 OR 垃圾 OR 衛生 OR 垃圾山 OR 回收績效",
        "sites": [
            "site:epa.gov.tw",
            "site:moenv.gov.tw",
            "site:udn.com",
            "site:ltn.com.tw",
            "site:chinatimes.com",
            "site:ettoday.net",
            "site:g0v.tw",
            "site:nownews.com",
            "site:thenewslens.com",
            "site:storm.mg",
            "site:newtalk.tw",
            "site:cna.com.tw",
            "site:ptt.cc",
            "site:mobile01.com",
            "site:news.google.com.tw"
        ]
    },
    "air quality": {
        "keywords": "空氣品質 OR PM2.5 OR AQI OR 空污 OR 監測站 OR 污染 OR 空氣 OR 空品",
        "sites": [
            "site:airtw.moenv.gov.tw",
            "site:moenv.gov.tw",
            "site:epa.gov.tw",
            "site:udn.com",
            "site:ltn.com.tw",
            "site:ettoday.net",
            "site:storm.mg",
            "site:ptt.cc",
            "site:mobile01.com"
        ]
    },
    "safety": {
        "keywords": "治安 OR 犯罪率 OR 刑案 OR 警局 OR 報案 OR 安全 OR 犯罪",
        "sites": [
            "site:police.gov.tw",
            "site:npa.gov.tw",
            "site:udn.com",
            "site:ltn.com.tw",
            "site:ettoday.net",
            "site:chinatimes.com",
            "site:ptt.cc",
            "site:mobile01.com"
        ]
    },
    "cost of living": {
        "keywords": "房價 OR 租金 OR 生活成本 OR 房租 OR 房市 OR 物價 OR 生活費 OR 實價登錄 OR 每坪",
        "sites": [
            "site:591.com.tw",
            "site:houseprice.tw",
            "site:catking.tw",
            "site:numbeo.com",
            "site:mobile01.com",
            "site:ptt.cc",
            "site:udn.com",
            "site:ltn.com.tw"
        ]
    },
}

TIME_FILTER = "113年 OR 114年 OR 2024 OR 2025"

# ────────────────────────────────────────────────
#  Helper functions
# ────────────────────────────────────────────────

def save_mappings(data, city, topic):
    filename = f"{city}_{topic}_data.json"
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def save_geojson(geojson_data, city, topic):
    filename = f"{city}_{topic}_map.geojson"
    with open(filename, "w") as f:
        json.dump(geojson_data, f, indent=4)


def extract_official_names(geojson_data_raw):
    if geojson_data_raw is None or not isinstance(geojson_data_raw, tuple) or geojson_data_raw[0] is None:
        print("ERROR: No GeoJSON data returned from get_city_geojson")
        return []

    geojson_data, target_location = geojson_data_raw
    
    if not geojson_data or not isinstance(geojson_data, dict):
        print("ERROR: GeoJSON is not a dict")
        return []

    features = geojson_data.get('features', [])
    print(f"Features count: {len(features)}")

    official_data = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get('properties', {})
        tags = props.get('tags', {})
        name_zh = props.get('name') or tags.get('name') or tags.get('name:zh')
        name_en = tags.get('name:en') or props.get('name:en') or name_zh
        if name_zh:
            official_data.append({
                'search_name': name_en,
                'display_name': name_zh
            })

    if not official_data:
        print("WARNING: No districts extracted")
    return official_data

# ────────────────────────────────────────────────
#  Main pipeline
# ────────────────────────────────────────────────
def run_pipeline_agent(city, topic, logger=print):
    """
    city: str
    topic: str
    logger: callable to receive live logs (default: print)
    """
    logger(f"🌍 Fetching boundaries for {city}...")

    geojson_data_raw = get_city_geojson(city)
    save_geojson(geojson_data_raw[0], city, topic)
#     official_names = extract_official_names(geojson_data_raw)

#     if not official_names:
#         logger("⚠️ No districts found.")
#         return

#     logger(f"Found {len(official_names)} districts.")
    
#     config = TOPIC_CONFIG.get(topic.lower(), {"keywords": topic, "sites": []})
#     topic_kws = config["keywords"]
#     topic_sites = " OR ".join(config["sites"])

#     final_results = []
#     for area in official_names:
#         zh_district = area['display_name']
#         logger(f"🔍 Checking {area['search_name']} ({zh_district})...")

#         specific_query = (
#             f"{zh_district} {topic_kws} "
#             f"{TIME_FILTER} "
#             f"{topic_sites}"
#         )

#         try:
#             area_info = serper_search(specific_query)
#             print(f"{area['search_name']}: {area_info[:300]}...")

#             score_prompt = f"""
# [CONTEXT] You are an urban expert in {city}.

# [DATA] {area_info}

# [TASK] Rate "{topic}" of {zh_district} from 0.00 (very poor) to 1.00 (excellent).

# [RUBRIC - use this scale STRICTLY]
# 0.00–0.30: Severe problems (major crises, widespread complaints, very low numbers/rankings)
# 0.31–0.45: Below average (clear negatives, low performance, frequent issues)
# 0.46–0.54: Neutral / average (no strong signal either way, basic competence)
# 0.55–0.69: Above average (some positives, moderate performance, few complaints)
# 0.70–0.85: Good (strong positives, high rankings/rates, praise)
# 0.86–1.00: Excellent (top-tier, exceptional evidence, consistent high marks)

# [GUIDELINES]
# - Only use content mentioning {zh_district} and related to {city} {topic}.
# - Use two decimal places always. No rounding to tenths unless evidence is overwhelming.
# - Small evidence differences → small score differences.
# - Positive (>0.50): strong indicators, high rankings/numbers.
# - Negative (<0.50): poor indicators, low numbers.

# [OUTPUT] Only a number with two decimals (e.g. 0.52). Nothing else.
# """

#             score_prompt_zh = translator.translate(score_prompt, dest='zh-tw').text
#             score_reply = llm.invoke(score_prompt_zh).content.strip()

#             print(f"Score: {score_reply}")

#             score_match = re.search(r"\d+\.\d{2}", score_reply)
#             score = float(score_match.group()) if score_match else 0.50
#             final_results.append(f"{area['search_name']}:{score:.2f}")

#         except Exception as e:
#             print(f"Error: {e}")
#             final_results.append(f"{area['search_name']}:0.50")


#     # Save results
#     mapping_data = {entry.split(":")[0]: float(entry.split(":")[1]) for entry in final_results}
#     save_mappings(mapping_data, city, topic)
#     logger(f"✅ Finished agent for {city}")

# ────────────────────────────────────────────────
#  Entry point
# ────────────────────────────────────────────────

if __name__ == "__main__":
    run_pipeline_agent("Tainan, Taiwan", "cleanliness")
    # Try also: "Taichung, Taiwan", "cleanliness", "Kaohsiung, Taiwan", "safety", etc.