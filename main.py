# main_langchain.py
import os
import json
from langchain_community.tools import DuckDuckGoSearchRun
import requests
from langchain_openai import ChatOpenAI
from langchain.agents import Tool, initialize_agent, AgentType
from langchain.prompts import PromptTemplate
from langchain.schema import SystemMessage, HumanMessage
import dotenv
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.memory import ConversationBufferMemory
# Environment
# ────────────────────────────────────────────────
dotenv.load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ddg = DuckDuckGoSearchRun()
wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
if not SERPER_API_KEY:
    raise ValueError("SERPER_API_KEY not set")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not set")


llm = ChatOpenAI(
    model="stepfun/step-3.5-flash:free",
    temperature=0,
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
)

# ────────────────────────────────────────────────
# Search functions
# ────────────────────────────────────────────────

def serper_search(query, max_results=6):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": max_results})
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    results = response.json()
    
    snippets = []

    # Include answer box if present
    if "answerBox" in results and results["answerBox"].get("answer"):
        snippets.append(results["answerBox"]["answer"])

    for r in results.get("organic", [])[:max_results]:
        snippets.append(f"{r.get('title','')} - {r.get('snippet','')}")

    # IMPORTANT: convert list to single string for agent
    return "\n\n".join(snippets)

# ────────────────────────────────────────────────
# LangChain Tools
# ────────────────────────────────────────────────
tools = [
    Tool(
        name="Serper",
        func=serper_search,
        description="Use this tool to search official government and PDF data online."
    ),
    Tool(
        name="DuckDuckGo",
        func=ddg.run,
        description="Use this tool to search general web content or recent news."
    ),
    Tool(
        name="Wikipedia",
        func=wiki.run,
        description="Use this tool to fetch historical or background information from Wikipedia."
    )
]

# ────────────────────────────────────────────────
# Query evaluation & scoring
# ────────────────────────────────────────────────
def evaluate_single_result(text, topic_keywords, district):
    text_lower = text.lower()
    score = 0.0
    # district match
    if district.lower() in text_lower:
        score += 0.4
    # topic keywords match
    for kw in topic_keywords:
        if kw.lower() in text_lower:
            score += 0.2
    # data-report signals
    data_keywords = ["統計", "數據", "報告", "年", "資料", "table", "statistics"]
    data_hits = sum(1 for k in data_keywords if k.lower() in text_lower)
    score += min(data_hits * 0.05, 0.15)
    # government sources
    if ".gov" in text_lower or ".gov.tw" in text_lower:
        score += 0.1
    return min(score, 1.0)

# ────────────────────────────────────────────────
# Agent Execution
# ────────────────────────────────────────────────

def score_district(data_file, district, city, country, topic, force_refresh=False, max_iters=3, logger=None):
    """
    Two-stage district scoring:
    Stage 1: Retrieval of top sources using agent
    Stage 2: Extract structured metrics from sources
    """

    topic_keywords = TOPIC_CONFIG.get(topic, {}).get('keywords', [topic])

    # --------------------------
    # Load cached data if available
    # --------------------------
    if not force_refresh and os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
            if district in cache:
                if logger: logger(f"📂 Using cached score for {district}")
                return cache[district]
    else:
        cache = {}

    # --------------------------
    # Stage 1: Retrieval
    # --------------------------
    chat_history = ChatMessageHistory()
    memory = ConversationBufferMemory(memory_key="chat_history", chat_memory=chat_history, return_messages=True)

    retrieval_agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        max_output_tokens=2000,
        verbose=True,
        handle_parsing_errors=True
    )

    retrieval_prompt = f"""
You are an expert urban data analyst.

Task: Collect **high-quality sources** about "{topic}" in {district}, {city}, {country}.

Use the following tools:
- Serper: official reports, PDFs
- DuckDuckGo: news, general web
- Wikipedia: historical or background information

Instructions:
1. Find at most 5 relevant snippets per tool.
2. Return only snippets that explicitly mention {district}.
3. Do NOT score or generate metrics yet — only find sources.
4. If the results are not going to be helpful for scoring the {topic} of {district}, keep searching until you find some that will be.

Format final output as JSON with this structure:
{{
    "action": "Final Answer",
    "sources": [
        {{
            "tool": "Serper",
            "text": "..."
        }}
    ]
}}
"""

    retrieval_response = retrieval_agent.invoke(retrieval_prompt)

    # Step 1: get response string
    retrieval_str = (
        retrieval_response["output"]
        if isinstance(retrieval_response, dict) and "output" in retrieval_response
        else retrieval_response
    )

    # Step 2: parse JSON safely
    try:
        action_json = json.loads(retrieval_str)
        sources = action_json.get("sources", [])
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        sources = []

    # Step 3: use sources safely
    print("Final Sources:", sources)

    # --------------------------
    # Stage 2: Structured Scoring
    # --------------------------
    # Prepare sources as a text block for LLM
    sources_text_block = "\n".join([f"{s['tool']}: {s['text']}" for s in sources])

    scoring_prompt = f"""

You are an expert municipal urban policy analyst.

Your task is to evaluate district-level conditions using aggregated evidence,
not isolated anecdotes.

District: "{district}"
City: {city}
Country: {country}
Topic: "{topic}"

Sources:
{sources_text_block}

INSTRUCTIONS:

1. Evaluate conditions at the DISTRICT LEVEL.
   - Do NOT generalize from a single localized complaint.
   - A single negative news article does NOT justify a "poor" rating.
   - Only assign "poor" or "very poor" if there is repeated, systemic,
     or district-wide evidence of persistent problems.

2. If evidence is mixed, limited, or mostly routine government reporting,
   default to "average".

3. Government monitoring reports, routine clean-up reports, or inspection
   activity indicate baseline functioning — not failure.

4. Positive civic activities (e.g., volunteer cleanups, upgrades,
   improvements) indicate active governance and should prevent overly
   negative scoring.

5. Be conservative with extreme ratings:
   - Use "excellent" only if there is strong evidence of exceptional performance.
   - Use "very poor" only if there is strong evidence of severe, systemic issues.

6. If insufficient evidence exists for a metric, assign "average".

Use ONLY the following scale for every metric:
"very poor", "poor", "average", "good", "excellent"

Metrics to include (fill with estimates if unknown):
Positive Metrics:
{TOPIC_CONFIG.get(topic).get('metrics').get("positive")}
Negative Metrics:
{TOPIC_CONFIG.get(topic).get('metrics').get("negative")}

Return JSON only.
Do NOT include explanations.
"""
    print("Retrieving Scores")
    # Call LLM directly (no tools)
    scoring_response = llm.invoke(scoring_prompt)
    # Parse JSON safely
    scoring_text = getattr(scoring_response, "content", scoring_response)
    print(scoring_text)
    try:
        metrics = json.loads(scoring_text)
    except Exception:
        metrics = {}

    # --------------------------
    # Stage 3: Convert metrics to numeric score
    # --------------------------
    def signals_to_score(metrics):
        """
        Converts structured metrics into a 0–1 overall score.
        All metrics use the same semantic scale:
        very poor -> 0.0
        poor -> 0.25
        average -> 0.5
        good -> 0.75
        excellent -> 1.0
        """

        if not metrics:
            return 0.5

        scale = {
            "very poor": 0.0,
            "poor": 0.25,
            "average": 0.5,
            "good": 0.75,
            "excellent": 1.0
        }

        total = 0.0
        count = 0

        for value in metrics.values():
            if isinstance(value, str):
                total += scale.get(value.lower(), 0.5)
                count += 1

        return round(total / count, 2) if count > 0 else 0.5

    score = signals_to_score(metrics)

    result = {
        "tool_results": sources,
        "metrics": metrics,
        "score": score
    }
    print(f"{district}, {city} has been scored at {score} for {topic}")
    # Save to cache
    cache[district] = result
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    return result

TOPIC_CONFIG = {
    "cleanliness-dirtiness": {
        'keywords': [
            # positive / neutral
            "cleanliness",        # English
            "整潔",               # tidy / clean
            "公共場所衛生",        # public area hygiene
            "環境衛生",           # environmental hygiene
            "垃圾清運",           # waste collection
            "清掃",               # cleaning / sweeping
            "衛生管理",           # sanitation management
            "清潔隊",             # sanitation crews

            # negative / filthiness
            "dirtiness",          # English
            "髒亂",               # dirty / messy
            "垃圾堆積",           # trash accumulation
            "違規棄置",           # illegal dumping
            "污染",               # pollution
            "衛生問題",           # hygiene issues
            "臭味",               # bad smell / odor
            "清潔不足",           # insufficient cleaning
            "環境髒亂"            # messy environment
        ],
        'metrics': {
            'positive': """
- overall_cleanliness (very poor, poor, average, good, excellent)
- street_cleanliness (very poor, poor, average, good, excellent)
- waste_management (very poor, poor, average, good, excellent)
- public_area_cleanliness (very poor, poor, average, good, excellent)
- park_cleanliness (very poor, poor, average, good, excellent)
- illegal_dumping_incidents (very poor, poor, average, good, excellent)
""",
            'negative': """
- odor_issues (very poor, poor, average, good, excellent)
- sanitation_compliance (very poor, poor, average, good, excellent; how well local rules and inspections are followed)
- community_engagement (very poor, poor, average, good, excellent; participation in clean-up or awareness activities)
"""
        }
    },
}