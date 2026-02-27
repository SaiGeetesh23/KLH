# import os
# from langchain_core.messages import HumanMessage, SystemMessage
# from langchain_core.tools import tool
# from langgraph.prebuilt import create_react_agent
# import pandas as pd
# from typing import Dict, Any

# # Global variable to hold dataframe in memory for the demo.
# # In a real app, you'd store it in a database or blob storage per user/session.
# _user_bank_data: Dict[str, pd.DataFrame] = {}

# def store_bank_data(thread_id: str, df: pd.DataFrame):
#      _user_bank_data[thread_id] = df

# def get_bank_data(thread_id: str) -> pd.DataFrame:
#      return _user_bank_data.get(thread_id)

# @tool
# def analyze_bank_statement(thread_id: str) -> str:
#     """Analyze the uploaded bank statement CSV to identify tax saving gaps and recommend options. Needs thread_id to get data."""
#     df = get_bank_data(thread_id)
#     if df is None:
#         return "Error: No bank statement data found. Please ask the user to upload a CSV file first."
    
#     # Process the dataframe to summarize transactions
#     # We take the negative of Debit amounts to make them positive for summarization
#     df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    
#     # Simple heuristic to identify debits (outflows)
#     debits = df[df['Amount'] < 0].copy()
#     debits['Amount'] = debits['Amount'].abs()
    
#     summary = "Here is a summary of the debit transactions found in the user's bank statement:\n\n"
#     for _, row in debits.iterrows():
#          summary += f"- {row['Date']} | {row['Description']} | Rs {row['Amount']}\n"
         
#     summary += "\nPlease review these transactions and categorize them into 80C and 80D investments (e.g., LIC, ELSS, PPF, Home Loan, Health Insurance).\n"
#     summary += "Then, calculate the utilized amount for 80C (Limit: 1.5 Lakh) and 80D (Limit: 25,000) and report the remaining gap.\n"
#     summary += "Finally, suggest specific investments to fill any remaining gap to maximize tax savings."
    
#     return summary

# def create_tax_agent():
#     """Creates the Tax-Saver Agent node for the langgraph supervisor."""
    
#     tax_system_prompt = """
# You are the Nivara Tax-Saver Agent, an expert in Indian Personal Wealth and Tax Planning.
# Your primary role is to help users maximize their tax savings by analyzing their bank statements and identifying gaps under Section 80C and Section 80D of the Income Tax Act.

# **Section 80C (Limit: ₹1,50,000/year):**
# Eligible: EPF, PPF, ELSS, LIC/Life Insurance, NPS, NSC, Tax-saving FDs, Home Loan Principal, Tuition Fees.

# **Section 80D (Limit: ₹25,000/year for self/family under 60):**
# Eligible: Medical/Health insurance premiums, Preventive health check-ups (up to ₹5,000).

# **Your Workflow:**
# 1. Use the `analyze_bank_statement` tool to retrieve a summary of the user's transactions (you will be provided the thread_id).
# 2. If no data is found, politely ask the user to upload their bank statement CSV.
# 3. If data is retrieved, carefully classify the transactions into 80C or 80D categories.
# 4. Calculate the total utilized amount for each section.
# 5. Calculate the remaining gap for each section (Limit - Utilized).
# 6. Generate a clear, easy-to-read structured report for the user that shows:
#    - What they have already invested (and under which section).
#    - Their remaining tax-saving potential (gaps).
#    - Specific recommendations on where to invest to fill the gap and maximize savings.
#    - Example: "You have a gap of ₹1,15,000 under 80C. You can consider investing in ELSS mutual funds for higher returns or PPF for safe returns."
   
# Be conversational, professional, and clear. Format your response nicely using markdown.
# """
    
#     # We must lazily import or provide the LLM. 
#     # For now we'll require the llm to be set during init
#     global tax_llm
#     if 'tax_llm' not in globals():
#         from langchain_openai import ChatOpenAI
#         tax_llm = ChatOpenAI(model='gpt-4o', temperature=0.1)
        
#     tax_agent = create_react_agent(
#         model=tax_llm,
#         tools=[analyze_bank_statement],
#         prompt=tax_system_prompt,
#         name='tax_agent'
#     )
    
#     return tax_agent

# def init_tax_agent(llm):
#     """Initialize the Tax Agent's LLM."""
#     global tax_llm
#     tax_llm = llm


import os
import pandas as pd
from typing import Dict
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

# -------------------------------------------------------
# In-memory storage (per thread_id)
# -------------------------------------------------------

_user_bank_data: Dict[str, pd.DataFrame] = {}


def store_bank_data(thread_id: str, df: pd.DataFrame):
    """Store uploaded bank statement using thread_id as key."""
    _user_bank_data[thread_id] = df


def get_bank_data(thread_id: str) -> pd.DataFrame:
    """Retrieve stored bank statement using thread_id."""
    return _user_bank_data.get(thread_id)


# -------------------------------------------------------
# TOOL: Analyze Bank Statement
# -------------------------------------------------------

@tool
def analyze_bank_statement(config: RunnableConfig) -> str:
    """
    Analyze the uploaded bank statement CSV to identify
    tax saving gaps and recommend options.
    """

    # 🔥 Get thread_id from LangGraph runtime config
    thread_id = config["configurable"]["thread_id"]

    df = get_bank_data(thread_id)

    if df is None:
        return "No bank statement data found. Please upload a CSV file first."

    df = df.copy()

    # Ensure Amount column is numeric
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    # Identify debit transactions (negative amounts)
    debits = df[df["Amount"] < 0].copy()
    debits["Amount"] = debits["Amount"].abs()

    if debits.empty:
        return "No debit transactions found in the uploaded statement."

    summary = "Here is a summary of the debit transactions found:\n\n"

    for _, row in debits.iterrows():
        date = row.get("Date", "Unknown Date")
        desc = row.get("Description", "No Description")
        amt = row.get("Amount", 0)

        summary += f"- {date} | {desc} | ₹{amt}\n"

    summary += "\nNow categorize the above transactions into:\n"
    summary += "- Section 80C eligible investments\n"
    summary += "- Section 80D eligible investments\n\n"

    summary += "Then calculate:\n"
    summary += "- Total utilized under 80C (Limit: ₹1,50,000)\n"
    summary += "- Total utilized under 80D (Limit: ₹25,000)\n"
    summary += "- Remaining gap under each section\n\n"

    summary += "Finally, suggest specific investment options to maximize tax savings."

    return summary


# -------------------------------------------------------
# TAX AGENT CREATION
# -------------------------------------------------------

def create_tax_agent():
    """Creates the Tax-Saver Agent node for LangGraph Supervisor."""

    tax_system_prompt = """
You are the Nivara Tax-Saver Agent.

IMPORTANT RULE:
For ANY user query related to tax, tax overview, tax report, 80C, 80D, or bank statement analysis —
YOU MUST ALWAYS CALL the `analyze_bank_statement` tool FIRST.

Do NOT assume the data is missing.
Do NOT ask the user to upload before checking.

Workflow:
1. ALWAYS call `analyze_bank_statement` tool.
2. If the tool returns "No bank statement data found" → THEN ask user to upload CSV.
3. If data is returned → analyze and generate full tax report.

Never skip calling the tool.


FORMAT:
Provide a clean structured markdown report including:
- Investments identified
- Total utilized under 80C
- Total utilized under 80D
- Remaining gap
- Clear actionable recommendations

Be professional, structured, and easy to read.
"""

    global tax_llm
    if "tax_llm" not in globals():
        from langchain_openai import ChatOpenAI
        tax_llm = ChatOpenAI(model="gpt-4o", temperature=0.1)

    tax_agent = create_react_agent(
        model=tax_llm,
        tools=[analyze_bank_statement],
        prompt=tax_system_prompt,
        name="tax_agent",
    )

    return tax_agent


def init_tax_agent(llm):
    """Initialize Tax Agent LLM."""
    global tax_llm
    tax_llm = llm