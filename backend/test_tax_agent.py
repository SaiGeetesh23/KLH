import os
from dotenv import load_dotenv

load_dotenv()

import pandas as pd
from Agents.tax_agent import init_tax_agent, create_tax_agent, store_bank_data, analyze_bank_statement
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Initialize the LLM
llm = ChatOpenAI(model='gpt-4o', temperature=0.1)
init_tax_agent(llm)

# Load the demo CSV
csv_path = "sample_bank_statement.csv"
print(f"Loading {csv_path}...")
df = pd.read_csv(csv_path)

# Mock a user context
thread_id = "test-user-123"
store_bank_data(thread_id, df)

# Check the tool output directly
print("\n--- Tool Output ---")
tool_output = analyze_bank_statement.invoke({"thread_id": thread_id})
print(tool_output)

# Check the Agent response
print("\n--- Tax Agent Response ---")
agent = create_tax_agent()
config = {"configurable": {"thread_id": thread_id}}

response = agent.invoke(
    {"messages": [HumanMessage(content="Please review my bank statement and give me a tax saving report.")]},
    config=config
)

for msg in response['messages']:
    if hasattr(msg, 'content') and msg.content:
        # Ignore tool call messages in output
        if msg.type == 'ai' and msg.content:
            print("AI:\n", msg.content, "\n")
