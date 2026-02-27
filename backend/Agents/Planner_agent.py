import joblib
import json
import numpy as np
import re
from typing import Tuple, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from graph_setup import memory

_loaded_model = None
_planner_agent_llm = None
planner_agent_prompt = None

def init_planner_agent(planner_agent_llm):
    """Initializes the Planner Agent by loading the joblib model and setting the LLM."""
    global _loaded_model, _planner_agent_llm, planner_agent_prompt
    _loaded_model = joblib.load('./Agents/investment_model.joblib')
    _planner_agent_llm = planner_agent_llm
    planner_agent_prompt = """
    You are PlannerAgent, an AI assistant that creates personalized investment plans for new Indian investors.

    **Your Mission:**
    1.  Your primary and only tool is `get_investment_plan`. This tool is state-aware; it will find the user's age and risk tolerance from their profile or the conversation.
    2.  Once the tool returns the asset allocation percentages (equity, debt, gold), your job is to translate these numbers into a clear, actionable, and encouraging plan for the user.
    3.  Explain *why* this allocation was chosen based on their profile. For example: "Given your age and high risk tolerance, the plan favors a higher allocation to equities for long-term growth..."
    4.  Present the final, comprehensive plan to the user in a simple, formatted way.

    **Investment Playbook (How to suggest products):**
    - For the `equity` portion: Always suggest a "Nifty 50 Index Fund" as a great starting point for diversification.
    - For the `debt` portion: Always suggest the "Public Provident Fund (PPF)" and mention its safety and tax benefits.
    - For the `gold` portion: Always suggest "Sovereign Gold Bonds (SGBs)" and mention they are a tax-efficient digital option issued by the RBI.

    **Behavior Rules:**
    - **Strictly follow the playbook.** Do not suggest individual stocks or any other products.
    - Your final response to the user should be the complete, formatted plan. Do not just output the raw numbers from the tool.
    - Be encouraging and clear, as you are guiding a new investor.
    """

def _extract_info_from_history(thread_id: str) -> Tuple[Optional[int], Optional[int]]:
    """Parses the last few messages in the conversation history to find age and risk tolerance."""
    age = None
    risk = None
    
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = memory.get_tuple(config)
    
    if not checkpoint_tuple:
        return None, None
        
    messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
    if not messages:
        return None, None

    # Check the last 6 messages
    for msg in reversed(messages[-6:]):
        content = getattr(msg, "content", "")
        if not isinstance(content, str):
            continue
        content = content.lower()
        age_match = re.search(r'\b(\d{2})\b', content)
        if age_match and not age:
            age = int(age_match.group(1))

        risk_match = re.search(r'\b([1-5])\b', content)
        if risk_match and not risk:
            risk = int(risk_match.group(1))
            
    return age, risk

@tool
def get_investment_plan(config: dict) -> str:
    """
    Generates a personalized investment plan. It intelligently retrieves the user's
    age and risk tolerance from their saved profile or the recent conversation history,
    and saves any new information back to their profile.
    """
    print("--- PLANNER AGENT: GENERATING STATE-AWARE PLAN ---")
    db: Session = SessionLocal()
    try:
        thread_id = config["configurable"]["thread_id"]
        
        user = db.query(models.User).filter(models.User.thread_id == thread_id).first()
        if not user:
            return json.dumps({"status": "error", "message": "Critical error: User not found for this session."})

        if not user.age or not user.risk_tolerance:
            print("User profile incomplete in DB. Parsing conversation history...")
            extracted_age, extracted_risk = _extract_info_from_history(thread_id)
            
            profile_updated = False
            if extracted_age and not user.age:
                user.age = extracted_age
                profile_updated = True
            if extracted_risk and not user.risk_tolerance:
                user.risk_tolerance = str(extracted_risk) 
                profile_updated = True
            
            if profile_updated:
                db.commit()
                db.refresh(user)
                print(f"User profile for {user.email} updated from conversation.")

        if not user.age or not user.risk_tolerance:
            return json.dumps({
                "status": "error", 
                "message": "Could not determine the user's age and risk tolerance. Please ensure the supervisor has asked for this information."
            })

        print(f"Running prediction for Age: {user.age}, Risk: {user.risk_tolerance}")
        params = np.array([[int(user.age), int(user.risk_tolerance)]])
        prediction = _loaded_model.predict(params)
        
        result = {
            "status": "success",
            "data": {
                'equity_pct': round(prediction[0][0], 2),
                'gold_pct': round(prediction[0][1], 2),
                'debt_pct': round(prediction[0][2], 2)
            }
        }
        return json.dumps(result)

    except Exception as e:
        print(f"An error occurred in get_investment_plan: {e}")
        return json.dumps({"status": "error", "message": f"An unexpected error occurred: {str(e)}"})
    finally:
        db.close()


def create_planner_agent():
    """Creates the LangGraph ReAct agent for financial planning."""
    planner_agent = create_react_agent(
        model=_planner_agent_llm,
        tools=[get_investment_plan],
        prompt=planner_agent_prompt,
        name='planner_agent'
    )
    return planner_agent