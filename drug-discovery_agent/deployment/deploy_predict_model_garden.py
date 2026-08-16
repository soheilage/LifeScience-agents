#!/usr/bin/env python3
"""
deploy_txgemma_model_garden.py - Deploy TxGemma Predict using the official Model Garden OpenModel API.
"""

import os
import sys
import dotenv
import vertexai
from vertexai.preview import model_garden

ENV_PATH = "/Users/soheila/adk-workspace/txgemma_demo/drug-discovery_agent/.env"
dotenv.load_dotenv(ENV_PATH, override=True)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "txgemma-501602")
LOCATION = "us-central1"
MACHINE_TYPE = "g2-standard-24"
ACCELERATOR_TYPE = "NVIDIA_L4"
ACCELERATOR_COUNT = 2
SPOT = True

print("==================================================")
print(f"🚀 Initializing Vertex AI Model Garden ({PROJECT_ID} / {LOCATION})")
print("==================================================")
vertexai.init(project=PROJECT_ID, location=LOCATION)

print("\n--> Fetching official Model Garden OpenModel for google/txgemma@txgemma-9b-predict...")
open_model = model_garden.OpenModel("google/txgemma@txgemma-9b-predict")

print("\n==================================================")
print(f"🚀 Deploying TxGemma 9B Predict to Vertex AI Endpoint")
print(f"   Machine: {MACHINE_TYPE} | GPU: {ACCELERATOR_TYPE} x{ACCELERATOR_COUNT} (Spot={SPOT})")
print("==================================================")

endpoint = open_model.deploy(
    accept_eula=True,
    machine_type=MACHINE_TYPE,
    accelerator_type=ACCELERATOR_TYPE,
    accelerator_count=ACCELERATOR_COUNT,
    min_replica_count=1,
    max_replica_count=1,
    spot=SPOT,
    endpoint_display_name="txgemma-9b-predict-endpoint",
    model_display_name="txgemma-9b-predict",
    use_dedicated_endpoint=True,
    deploy_request_timeout=1800,
)

endpoint_id = endpoint.name
print(f"\n==================================================")
print(f"🎉 SUCCESS! TxGemma 9B Predict deployed via Model Garden!")
print(f"👉 ENDPOINT ID: {endpoint_id}")
print(f"==================================================")

# Update .env
with open(ENV_PATH, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.startswith("TXGEMMA_PREDICT_ENDPOINT_ID="):
        new_lines.append(f'TXGEMMA_PREDICT_ENDPOINT_ID="{endpoint_id}"\n')
    elif line.startswith("TXGEMMA_PREDICT_LOCATION="):
        new_lines.append(f'TXGEMMA_PREDICT_LOCATION="{LOCATION}"\n')
    else:
        new_lines.append(line)

with open(ENV_PATH, "w") as f:
    f.writelines(new_lines)
print(f"📝 Updated .env with TXGEMMA_PREDICT_ENDPOINT_ID={endpoint_id} and TXGEMMA_PREDICT_LOCATION={LOCATION}")
