import os
import re
import logging
from datetime import datetime
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from langchain_community.utilities import SQLDatabase
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain.chains import create_sql_query_chain
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from operator import itemgetter
import tiktoken
from dotenv import load_dotenv
load_dotenv()

# -------------------------------
# Logging Setup
# -------------------------------
log_filename = "query_logs.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------------
# FastAPI App Setup
# -------------------------------
app = FastAPI(
    title="Kabaddi Text-to-SQL API",
    description="Ask natural language questions over Kabaddi data",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Pydantic Schemas
# -------------------------------
class QueryRequest(BaseModel):
    question: str

class QueryData(BaseModel):
    answer: str
    query: str
    tokens_used: int

class QueryResponse(BaseModel):
    status: str
    data: QueryData
    timestamp: str

# -------------------------------
# Environment and Config
# -------------------------------
EXCEL_PATH = "SKDB.xlsx"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# SYSTEM_PROMPT_TEMPLATE = """
# You are a SQLite expert. Given a natural language input question, perform the following steps:

# 1. Understand the user's intent.
# 2. Generate a syntactically correct and executable **SQLite** query.
# 3. Use only the tables described below. Do not hallucinate or assume additional tables or columns.
# 4. Limit results to a maximum of {top_k}, if applicable.

# ## Matching Rules:
# - All string/text comparisons must be **case-insensitive**.
# - Use `LOWER(column_name) = LOWER('value')` or `COLLATE NOCASE`.

# ## Allowed Tables:
# {table_info}

# Question: {input}
# """

SYSTEM_PROMPT_TEMPLATE = """
You are a SQLite expert and Kabaddi domain analyst. Given a user’s natural language question, follow these steps:

---

## Step-by-Step Instructions:

1. Understand the question intent, even if the input has typos, informal phrasing, or fuzzy terms.
2. Map Kabaddi-specific terms (e.g., "left raider", "defense of 3", "middle position") to correct SQL filters.
3. Generate a correct, executable SQLite query using only the allowed table and columns.
4. Always LIMIT results to a maximum of {top_k}, unless the question asks for all rows.

---

## ⚙️ Column Schema Allowed (from Excel Sheet):

{table_info}

---

## 🧠 Domain-Aware Natural Language → SQL Mappings:

| Natural Language Term           | SQL Logic or Transformation                                                |
|--------------------------------|-----------------------------------------------------------------------------|
| defense of 3                   | IsSuperTackleSituation = 1                                                  |
| less than 4 defenders          | IsSuperTackleSituation = 1                                                  |
| super tackle chance            | IsSuperTackleSituation = 1                                                  |
| regular defense (4+)           | IsSuperTackleSituation = 0 OR IsSuperTackleSituation IS NULL                |
| left raider                    | RaiderName LIKE '%_LIN_%'                                                   |
| right raider                   | RaiderName LIKE '%_RIN_%'                                                   |
| left corner tackle             | Tackle_Skill LIKE '%LCNR%'                                                  |
| right corner tackle            | Tackle_Skill LIKE '%RCNR%'                                                  |
| action in middle               | "ActionOnMat (LCNR_LIN_LCV_M_RCV_RIN_RCNR)" LIKE '___1___'                 |
| action on left corner + right cover | "ActionOnMat (LCNR_LIN_LCV_M_RCV_RIN_RCNR)" LIKE '1__0_1__'         |
| successful raid                | RaidStatus COLLATE NOCASE IN ('Successful', '1', '2')                       |
| unsuccessful raid              | RaidStatus COLLATE NOCASE IN ('Failed/Unsuccessful', '3')                   |
| bonus raid                     | IsBonus = 1                                                                 |
| do-or-die raid (DOD)           | DOD = 1                                                                     |
| tackle success                 | TackleStatus COLLATE NOCASE = 'Successful'                                  |
| all out inflicted              | AllOutInflictedBy IS NOT NULL                                               |
| period 1 / first half          | Period = 1                                                                  |
| period 2 / second half         | Period = 2                                                                  |
| hand touch                     | Raid_Skill LIKE '%HandTouch%'                                               |
| standing bonus                 | Raid_Skill LIKE '%StandingBonus%'                                           |
| team A score                   | RaidEnd_TeamAScore                                                           |
| team B score                   | RaidEnd_TeamBScore                                                           |
| match video URL                | URL                                                                          |

---

## 🧬 Player Name Structure:

All player names follow the format:
→ `<PlayerFullName>_<MainPlayingPosition>_<TeamShortCode><JerseyNumber>`

Examples:
- `Aslam Inamdar_LIN_PU3` → Left raider (LIN), Team = Puneri Paltan (PU)
- Use `_LIN_` and `_RIN_` inside names to infer Left/Right raider
- Use team code (PU, HS, etc.) for team identification

---

## 🧭 PositionOnMat Binary Codes:

The `"ActionOnMat (LCNR_LIN_LCV_M_RCV_RIN_RCNR)"` column is a **7-digit binary string**:
Each digit represents a position. From left to right:

| Index | Digit | Position      |
|-------|-------|---------------|
| 1     | 1     | LCNR (Left Corner) |
| 2     | 2     | LIN  (Left In)     |
| 3     | 3     | LCV  (Left Cover)  |
| 4     | 4     | M    (Middle)      |
| 5     | 5     | RCV  (Right Cover) |
| 6     | 6     | RIN  (Right In)    |
| 7     | 7     | RCNR (Right Corner)|

Example:
- `'0001000'` → Action at Middle
- `'1010100'` → Action at LCNR + LCV + RCV
Use SQL LIKE patterns to filter positions.

---
The last three digits in the Unique_Raid_Identifier is the raid sequence of the Match. This raid sequence shows the number of raids that has happened in the match.
- given by srikanth my manager

Automatically wrap subqueries with a WITH clause if a closing ) is followed by a SELECT, and the CTE is not declared properly.


---

## 🏏 Team Abbreviations:

| Code | Team Name             |
|------|------------------------|
| BW   | Bengal Warriors        |
| BB   | Bengaluru Bulls        |
| DD   | Dabang Delhi           |
| GG   | Gujarat Giants         |
| HS   | Haryana Steelers       |
| JP   | Jaipur Pink Panthers   |
| PP   | Patna Pirates          |
| PU   | Puneri Paltan          |
| TN   | Tamil Thalaivas        |
| TT   | Telugu Titans          |
| UM   | U Mumba                |
| UP   | U.P. Yoddhas           |

---

## ⚠️ Matching & SQL Rules:

- Always apply **case-insensitive matching** using `COLLATE NOCASE` or `LOWER() = LOWER()`.
- Never use columns not in the schema.
- Do not hallucinate missing values or structure.
- If using `UNION`, place `LIMIT` after the complete union, not in individual SELECTs.

---

## Output Expectations:

- Only output the final SQLite query — no explanation or extra commentary.
- If the question cannot be answered, return a SQL error with reason, do **not** guess results.

---

Question: {input}
"""


ANSWER_PROMPT_TEMPLATE = """
Given the following user question, corresponding SQL query, and SQL result, respond by formatting the SQL result into a clear, structured table format based on the intent of the question.
- Do NOT hallucinate or generate data that is not present in the SQL result.
- Use relevant key names derived from the result columns and context of the question.
- Only include keys present in the SQL result.
- If the result is a list of items, present it as a table with corresponding correct column names.
- If the result is a numeric-only aggregate (e.g., COUNT, SUM, AVG), return a simple sentence answer in natural language.

Question: {question}
SQL Query: {query}
SQL Result: {result}
Answer:
"""

# -------------------------------
# Utilities
# -------------------------------
def clean_sql_query(text: str) -> str:
    text = re.sub(r"```(?:sql)?\s*(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"^(SQLQuery:|SQL:|MySQL:|PostgreSQL:)\s*", "", text, flags=re.IGNORECASE)
    match = re.search(r"(SELECT.*?;)", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r'\s+', ' ', match.group(1).strip())
    return text.strip()

def load_excel():
    xl = pd.ExcelFile(EXCEL_PATH)
    return {
        name: xl.parse(name).to_dict(orient="records")
        for name in xl.sheet_names  # Load all sheets
    }

def load_into_sqlite(tables):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for name, rows in tables.items():
        pd.DataFrame(rows).to_sql(name, engine, index=False, if_exists='replace')
    return engine

# -------------------------------
# LangChain Setup
# -------------------------------
class KabaddiSystem:
    def __init__(self):
        tables = load_excel()
        self.engine = load_into_sqlite(tables)
        self.db = SQLDatabase(self.engine)
        self.table_info = self.db.get_table_info()

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-preview-05-20",
            temperature=0,
            google_api_key=GEMINI_API_KEY
        )

        self.generate_query = create_sql_query_chain(
            self.llm,
            self.db,
            prompt=PromptTemplate(
                input_variables=["input", "table_info", "top_k"],
                template=SYSTEM_PROMPT_TEMPLATE
            ),
            k=None
        )

        self.execute_query = QuerySQLDataBaseTool(db=self.db)
        self.rephrase_answer = PromptTemplate.from_template(ANSWER_PROMPT_TEMPLATE) | self.llm | StrOutputParser()
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def answer(self, question: str) -> dict:
        logger.info(f"Received question: {question}")
        logger.info(f"table_info: {self.table_info}...!")
        prompt_str = SYSTEM_PROMPT_TEMPLATE.format(input=question, table_info=self.table_info, top_k="5")
        input_tokens = len(self.encoder.encode(prompt_str))
        logger.info(f"input_tokens: {input_tokens}...!")

        try:
            chain = (
                RunnablePassthrough.assign(table_info=lambda x: self.table_info)
                | RunnablePassthrough.assign(
                    raw_query=self.generate_query,
                    query=self.generate_query | RunnableLambda(clean_sql_query)
                )
                | RunnablePassthrough.assign(
                    result=itemgetter("query") | self.execute_query
                )
                | RunnableLambda(lambda x: {
                    "answer": "No data available." if not x["result"].strip() else self.rephrase_answer.invoke({
                        "question": question,
                        "query": x["query"],
                        "result": x["result"]
                    }),
                    "query": x["query"],
                    "raw_results": x["result"]
                })
            )

            response = chain.invoke({"question": question, "messages": []})
            logger.info(f"Generated SQL query: {response['query']}")
            output_tokens = len(self.encoder.encode(response["answer"]))
            logger.info(f"output_tokens: {output_tokens}...!")

            total_tokens = input_tokens + output_tokens
            logger.info(f"total_tokens: {total_tokens}...!")

            logger.info(f"Final answer: {response['answer']}")

            return {
                "status": "success",
                "data": QueryData(
                    answer=response["answer"],
                    query=response["query"],
                    tokens_used=total_tokens
                ).dict(),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in answer method: {e}")
            return {
                "status": "error",
                "data": QueryData(
                    answer="",
                    query="",
                    tokens_used=input_tokens
                ).dict(),
                "timestamp": datetime.now().isoformat()
            }

# -------------------------------
# Initialize System
# -------------------------------
try:
    system = KabaddiSystem()
    logger.info("Kabaddi FastAPI initialized successfully.")
except Exception as e:
    logger.error(f"System init failed: {e}")
    system = None

# -------------------------------
# API Endpoints
# -------------------------------
@app.get("/")
async def root():
    return {
        "message": "Kabaddi Text-to-SQL API is running!",
        "endpoints": {
            "POST /ask": "Ask a question about Kabaddi data",
            "GET /health": "Health check",
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy" if system else "unhealthy",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/ask", response_model=QueryResponse)
async def ask(request: QueryRequest):
    if not system:
        logger.error("System not initialized when handling /ask endpoint.")
        raise HTTPException(status_code=500, detail="System not initialized")

    if not request.question.strip():
        logger.warning("Received empty question in /ask endpoint.")
        raise HTTPException(status_code=400, detail="Question is empty")

    try:
        logger.info(f"/ask endpoint received question: {request.question}")
        result = system.answer(request.question)
        logger.info(f"/ask endpoint returning result: {result}")
        return result

    except Exception as e:
        logger.error(f"Query failed in /ask endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed. Please try again.")

# -------------------------------
# Run with: uvicorn kabaddi_api:app --reload
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
