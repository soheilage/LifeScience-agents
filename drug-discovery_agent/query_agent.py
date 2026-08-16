#!/usr/bin/env python3
"""
query_agent.py - Query the deployed Drug Discovery Agent (agentic-tx) on Vertex AI Agent Platform.
"""

import os
import dotenv
import vertexai
from vertexai import agent_engines

# 1. Load environment variables
ENV_PATH = "/Users/soheila/adk-workspace/txgemma_demo/drug-discovery_agent/.env"
dotenv.load_dotenv(ENV_PATH, override=True)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "txgemma-501602")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = "1841578072675975168"

# 2. Initialize Vertex AI
print(f"Connecting to Vertex AI Agent Platform ({PROJECT_ID} / {LOCATION})...")
vertexai.init(project=PROJECT_ID, location=LOCATION)

agent = agent_engines.get(AGENT_ENGINE_ID)
print(f"✅ Connected to Agent: {agent.display_name} (ID: {agent.name})")

# 3. Create Session
user_id = "researcher_1"
session = agent.create_session(user_id=user_id)
session_id = session["id"] if isinstance(session, dict) else session.name
print(f"✅ Session Created: {session_id}")

# 4. Stream Query
query = "Can you identify the compound with SMILES CC(=O)OC1=CC=CC=C1C(=O)O and predict its clinical toxicity?"
print(f"\n💬 Query: {query}\n" + "-"*50)

for event in agent.stream_query(message=query, user_id=user_id, session_id=session_id):
    if isinstance(event, dict) and "content" in event and event["content"]:
        parts = event["content"].get("parts", [])
        for p in parts:
            if "text" in p and p["text"]:
                print(p["text"], end="", flush=True)

print("\n" + "-"*50 + "\n✅ Query completed successfully!")
