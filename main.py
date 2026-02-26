# main.py

import re
import json
import os
import requests
import dotenv
from langchain_openai import ChatOpenAI
from map_tool import get_city_geojson
from googletrans import Translator

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

# ────────────────────────────────────────────────
# Search
# ────────────────────────────────────────────────

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

def ensure_geojson(city, topic):
    """
    Ensures GeoJSON file exists for city and that it contains features.
    """
    geo_file = f"{city}_{topic}_map.geojson"

    if not os.path.exists(geo_file):
        geojson_data_raw = get_city_geojson(city)
        if geojson_data_raw and geojson_data_raw[0]:
            geojson_data = geojson_data_raw[0]

            # Validate
            if not isinstance(geojson_data, dict):
                raise ValueError("GeoJSON is not a dictionary")
            if "features" not in geojson_data or not geojson_data["features"]:
                raise ValueError("GeoJSON has no features")

            # Save validated GeoJSON
            with open(geo_file, "w") as f:
                json.dump(geojson_data, f, indent=4)
        else:
            raise ValueError("Failed to fetch GeoJSON")

    return geo_file

# ────────────────────────────────────────────────
# Scoring Engine (Single District)
# ────────────────────────────────────────────────

def score_district(city, topic, district, logger=print):
    """
    Scores ONE district and returns float.
    Uses cached value if available.
    """

    data_file = f"{city}_{topic}_data.json"

    # ───── Check Cache ─────
    if os.path.exists(data_file):
        with open(data_file) as f:
            existing = json.load(f)
            if district in existing:
                logger("📂 Using cached score")
                return existing[district]
    else:
        existing = {}

    logger(f"🔍 Searching data for {district}...")

    config = TOPIC_CONFIG.get(topic.lower(), {"keywords": topic, "sites": []})
    topic_kws = config["keywords"]
    topic_sites = " OR ".join(config["sites"])

    query = (
        f"{district} {topic_kws} "
        f"{TIME_FILTER} "
        f"{topic_sites}"
    )

    area_info = serper_search(query)

    logger("🤖 Running LLM scoring...")

    score_prompt = f"""
You are an urban analyst in {city}.

DATA:
{area_info}

TASK:
Rate "{topic}" of {district} from 0.00 (very poor) to 1.00 (excellent).

Use two decimal places strictly.
Return ONLY a number like 0.52.
"""

    score_prompt_zh = translator.translate(score_prompt, dest='zh-tw').text
    score_reply = llm.invoke(score_prompt_zh).content.strip()

    match = re.search(r"\d+\.\d{2}", score_reply)
    score = float(match.group()) if match else 0.50

    logger(f"✅ Score: {score:.2f}")

    # ───── Save Cache ─────
    existing[district] = score
    with open(data_file, "w") as f:
        json.dump(existing, f, indent=4)

    return score