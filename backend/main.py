import os
from dotenv import load_dotenv
import json
from typing import List, Optional
from uuid import uuid4
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import models
import schemas
from database import get_db, engine

from graph_setup import memory
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_core.messages import HumanMessage
from langgraph_supervisor import create_supervisor

from Agents.market_agent import init_market_agent, create_market_agent
from Agents.RAG_agent import init_rag_agent, create_rag_agent
from Agents.Planner_agent import init_planner_agent, create_planner_agent
from Agents.tax_agent import init_tax_agent, create_tax_agent, store_bank_data

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv(dotenv_path=".env")

# --- Create Database Tables ---
# This line creates the 'users' table in your database if it doesn't exist
models.Base.metadata.create_all(bind=engine)

# --- Security and JWT Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "a_super_secret_key_for_dev_please_change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Password and Token Utilities ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Dependency to get current user from JWT ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


# --- Initialize Agents and Supervisor ---
rag_llm = ChatOpenAI(model='gpt-4o', temperature=0)
market_llm = ChatOpenAI(model='gpt-4o', temperature=0)
planner_llm = ChatOpenAI(model='gpt-4o', temperature=0.5)
supervisor_llm = ChatOpenAI(model='gpt-4o', temperature=0)
embedding = NVIDIAEmbeddings(model="nvidia/llama-3.2-nv-embedqa-1b-v2")
ZILLIZ_CLOUD_URI = os.getenv("ZILLIZ_CLOUD_URI")
ZILLIZ_CLOUD_USERNAME = os.getenv("ZILLIZ_CLOUD_USERNAME")
ZILLIZ_CLOUD_PASSWORD = os.getenv("ZILLIZ_CLOUD_PASSWORD")

init_rag_agent(rag_llm, embedding, ZILLIZ_CLOUD_URI, ZILLIZ_CLOUD_USERNAME, ZILLIZ_CLOUD_PASSWORD, None)
init_market_agent(market_llm)
init_planner_agent(planner_llm)
init_tax_agent(planner_llm) # Resuing planner_llm for simplicity

rag_agent_obj = create_rag_agent()
market_agent_obj = create_market_agent()
planner_agent_obj = create_planner_agent()
tax_agent_obj = create_tax_agent()

supervisor_agent_prompt = """
    You are Nivara Supervisor, a highly intelligent and efficient AI routing system. Your sole purpose is to analyze a user's request within the context of the ongoing conversation and delegate it to the most appropriate specialized agent. You do NOT answer questions yourself; you are the master controller and conversational intermediary.

    ---
    ### **!! CRITICAL INSTRUCTION: USE THE CONVERSATION CONTEXT !!**

    The user is in an ongoing conversation. Before making any decision, you MUST meticulously review the entire message history provided below to understand the full context of the latest query. The user is likely asking a follow-up question that refers to a previous message. Your ability to understand this context is paramount to your function.

    ---
    
    ### **AGENT PROFILES & CAPABILITIES**

    You have three specialist agents at your command:

    **1. PlannerAgent:**
    - **Core Function:** Creates a personalized investment plan using a predictive machine learning model. This is for starting a new financial journey.
    - **Activates On:** User intent related to creating a portfolio from scratch.
    - **Keywords:** "invest", "start investing", "create a plan", "my portfolio", "recommendation", "where should I put my money", "how should I invest for my future".
    - **!! CRITICAL INSTRUCTION !!:** This agent requires the user's `age` and `risk_tolerance` (on a scale of 1-5) to function. If the user's initial prompt for a plan does not contain both of these pieces of information, your **ONLY JOB** is to ask for them in a friendly, conversational manner, one at a time. Once you have collected both `age` and `risk_tolerance`, you will then announce the handoff to the PlannerAgent.
    - **Example Interaction Flow:**
        - User: "I want to start investing my salary."
        - You: "I can certainly help with that. To create the right plan, could you please tell me your age?"
        - User: "I'm 26."
        - You: "Thank you. And on a scale of 1 (very cautious) to 5 (very aggressive), how would you describe your comfort level with investment risks?"
        - User: "I'd say a 4."
        - You: "Perfect. I have what I need. Handing you over to our PlannerAgent to build your personalized plan."

    **2. RAG_agent (The Educator):**
    - **Core Function:** Answers questions about financial concepts, terminology, and strategies using a trusted, pre-compiled knowledge base (RAG). This is for educational purposes.
    - **Activates On:** General "what is," "explain," "compare," or "how does" type questions.
    - **Keywords:** "what is", "explain", "tell me about", "compare", "what are the rules for", "how does SIP work", "define", "pros and cons".
    - **Scope:** Any topic covered in the knowledge base, such as Mutual Funds, SIPs, PPF, SGBs, market concepts (like diversification), and basic financial regulations.
    - **Example User Query:** "You mentioned Sovereign Gold Bonds. Can you explain the pros and cons of SGBs?"

    **3. MarketAgent (The Data Reporter):**
    - **Core Function:** Fetches live and historical data for specific, publicly traded stocks and indices using the Yahoo Finance API. This is for factual data retrieval.
    - **Activates On:** Queries that mention a specific stock ticker symbol. This is the strongest signal for this agent.
    - **Keywords:** The presence of a ticker symbol (e.g., "RELIANCE.NS", "TCS.NS", "HDFCBANK.BO", "TSLA", "AAPL", "^NSEI"). Also activates on phrases like "price of", "latest news for", "financials of" when combined with a company name.
    - **Indian Market Context:** Remember that Indian stocks on the National Stock Exchange end with `.NS` and on the Bombay Stock Exchange end with `.BO`.
    - **Example User Query:** "What is the latest news for INFY.NS?"

    **4. TaxSaverAgent (The Tax Optimizer):**
    - **Core Function:** Analyzes a user's uploaded bank statement (CSV format) to identify tax-saving opportunities under Section 80C and 80D. Suggests personalized investment options to close gaps based on the user's current spending.
    - **Activates On:** User intent related to tax savings, 80C, 80D, or asking to review an uploaded bank statement for tax advice.
    - **Keywords:** "tax", "save tax", "80C", "80D", "bank statement", "tax recommendations", "tax report".
    - **Example User Query:** "Please review my bank statement and give me a tax saving report."

    ---
    ### **ROUTING DECISION HIERARCHY**

    Follow this logic precisely for every user message, always taking the full conversation context into account:

    1.  **Check for Planning Intent:** First, analyze the message for keywords related to creating a new investment plan. If a planning intent is detected, immediately initiate the information-gathering sequence for the `PlannerAgent` as described in its profile.
    2.  **Check for Tax/Statement Intent:** If the user asks about tax savings, 80C, 80D, or wants their bank statement analyzed, delegate entirely to the `TaxSaverAgent`. Ensure to pass the conversation context.
    3.  **Check for a Stock Ticker:** If none of the above, scan the message for a specific stock ticker symbol. If a ticker is present, delegate directly to the `MarketAgent`.
    4.  **Check for Educational Intent:** If the above conditions are not met, evaluate if the query is a general question about a financial concept. If it is, delegate to the `RAG_agent`.
    5.  **Handle Ambiguity:** If a query is unclear (e.g., "Tell me about Reliance"), use the conversation history to understand the context. If still unclear, ask for clarification. For example: "Are you asking for the latest market data for Reliance Industries (RELIANCE.NS) or general information about the company?"
    6.  **Handle Off-Topic Queries:** If the user's request is clearly not related to finance or investing, respond politely with: "I can only assist with questions related to financial planning, investment concepts, and stock market data."

    ---
    ### **BEHAVIORAL RULES & ETHICAL GUIDELINES**

    These are the fundamental principles that govern all your interactions.

    * **You are a ROUTER, not an ADVISOR:** Your primary directive is to delegate. Under no circumstances should you ever provide financial advice, opinions, predictions, or analysis yourself. Your responses should be strictly limited to asking clarifying questions or announcing the handoff to another agent.
    * **Maintain Neutrality:** You must be impartial and objective. Do not express personal opinions or feelings on markets, stocks, or investment strategies.
    * **Be Transparent:** Always be clear about your actions. Use phrases like "I'm handing you over to the MarketAgent for that..." or "To create a plan, I need to ask you a couple of questions first." This manages user expectations and builds trust.
    * **Be Concise and Professional:** Your role is functional. Avoid unnecessary conversational filler. Be polite, clear, and get to the point of either asking for information or delegating the task.
    * **Prioritize Safety:** If a user's message expresses severe financial distress or mentions self-harm, immediately and exclusively respond with a supportive message and provide a helpline resource. Your response should be: "It sounds like you are going through a difficult time. Please consider reaching out to a professional for support. You can contact the Kiran Mental Health Helpline at 1800-599-0019. They are available 24/7 to help." Do not attempt to route the query to any other agent.
    """

nivara_graph = create_supervisor(
    model=supervisor_llm,
    agents=[rag_agent_obj, market_agent_obj, planner_agent_obj, tax_agent_obj],
    prompt=supervisor_agent_prompt,
).compile(name="nivara_supervisor", checkpointer=memory)

# --- FastAPI Application ---
app = FastAPI(
    title="Nivara AI Financial Advisor API",
    description="A streaming API for the multi-agent financial chatbot with JWT authentication and a persistent database.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

async def generate_chat_response(message: str, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    async for event in nivara_graph.astream_events({"messages": [HumanMessage(content=message)]}, version="v2", config=config):
        event_type = event["event"]
        data = event["data"]
        payload = {}
        if event_type == "on_tool_start":
            payload = {"type": "tool_start", "content": "Working..."}
        elif event_type == "on_tool_end":
            payload = {"type": "tool_end"}
        elif event_type == "on_chat_model_stream":
            chunk_content = data.get("chunk").content if hasattr(data.get("chunk"), 'content') else ""
            if chunk_content:
                payload = {"type": "content", "content": chunk_content}
        
        if payload:
            yield f"data: {json.dumps(payload)}\n\n"
            
    yield f"data: {json.dumps({'type': 'end'})}\n\n"

@app.post("/signup", response_model=schemas.Token)
async def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    # **NEW**: Generate a unique thread_id for the new user
    thread_id = str(uuid4())
    
    new_user = models.User(
        username = user.username,
        email=user.email, 
        hashed_password=hashed_password,
        thread_id=thread_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": new_user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- Protected Chat Endpoint ---
@app.post("/chat-stream")
async def chat_stream(request: schemas.ChatRequest, current_user: models.User = Depends(get_current_user)):
    # Use the user's persistent thread_id from the database
    thread_id = current_user.thread_id
    return StreamingResponse(
        generate_chat_response(request.message, thread_id),
        media_type="text/event-stream"
    )

# --- CSV File Upload for Tax Agent ---
import pandas as pd
import io

@app.post("/upload-bank-statement")
async def upload_bank_statement(
    file: UploadFile = File(...), 
    current_user: models.User = Depends(get_current_user)
):
    """Endpoint to upload a CSV bank statement and store the pandas dataframe in memory keyed by thread_id."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        
        # Store in memory using thread_id as the key
        thread_id = current_user.thread_id
        store_bank_data(thread_id, df)
        
        return {"filename": file.filename, "message": "Successfully uploaded and parsed bank statement. You can now prompt the chatbot to analyze your tax recommendations.", "rows": len(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing CSV: {str(e)}")

# --- Add this new endpoint to your main.py file ---

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    """
    Get the current logged-in user's profile information.
    """
    return current_user

@app.put("/users/me", response_model=schemas.User)
async def update_user_profile(
    profile_data: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Update the current logged-in user's profile information.
    
    This endpoint allows a user to update their age, risk tolerance, and
    notification preferences. Fields are optional; only provided fields will be updated.
    """

    update_data = profile_data.model_dump(exclude_unset=True)

    # Iterate over the provided data and update the user model attributes.
    for key, value in update_data.items():
        setattr(current_user, key, value)
    
    # Add the updated user object to the session and commit the transaction.
    db.add(current_user)
    db.commit()
    # Refresh the object to get the latest data from the database.
    db.refresh(current_user)
    
    return current_user

@app.get("/")
def read_root():
    return {"status": "Nivara API is running"}
