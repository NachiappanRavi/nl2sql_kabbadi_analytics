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
EXCEL_PATH = "KDB.xlsx"
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
You are a world-class SQLite expert. Given a natural language input question, follow these steps:

1. **Understand the user's intent** clearly.
2. **Generate a fully syntactically correct, executable SQLite query**.
3. Use **only the tables and columns listed below**. Do **not assume** the existence of any additional data.
4. If applicable, **limit output to a maximum of {top_k} rows** using `LIMIT`.
5. Use **Common Table Expressions (WITH clauses)** for multi-step logic. Each CTE must start with `WITH`, and each must be properly enclosed in parentheses and comma-separated if multiple are used.
6. **Ensure clean, valid SQL syntax**:
   - Avoid missing parentheses, extra commas, or invalid joins.
   - Always begin a CTE block with `WITH cte_name AS (...)`.
   - Avoid starting a SQL query with a raw `SELECT` when you're defining intermediate logic — use CTEs.
7. For case-insensitive text comparisons, use either:
   - `LOWER(column_name) = LOWER('value')`, or
   - `COLLATE NOCASE`
8. If dividing values (e.g., A / B), ensure the denominator is non-zero using `WHERE B > 0` or safe logic.
9. Prefer **explicit joins** with meaningful aliases and avoid unnecessary nesting.

## Allowed Tables:
{table_info}

## Input Question:
{input}

## Output:
Return only the final **SQLite query** that answers the question — with correct syntax and accurate logic.
"""



ANSWER_PROMPT_TEMPLATE = """
Given the following user question, SQL query, and SQL result, respond by formatting the result into a structured natural language response.

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
