# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tool for general therapeutic questions using a TxGemma Chat Vertex AI endpoint."""

import os
import vertexai
from google.cloud import aiplatform

# Initialize Vertex AI SDK
vertexai.init(
    project=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUD_ML_PROJECT_ID") or os.environ.get("PROJECT_ID"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

def ask_therapeutics_expert(query: str) -> str:
    """
    Answers general therapeutics questions using a TxGemma chat model.

    Args:
        query: The user's question about a therapeutic topic.

    Returns:
        A string containing the answer from the chat model.
    """
    # This environment variable must be set to your deployed TxGemma chat endpoint ID.
    endpoint_id = os.environ.get("TXGEMMA_CHAT_ENDPOINT_ID")
    if not endpoint_id:
        return "Error: TXGEMMA_CHAT_ENDPOINT_ID environment variable is not set."

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUD_ML_PROJECT_ID") or os.environ.get("PROJECT_ID") or "txgemma-501602"
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    endpoint = aiplatform.Endpoint(
        endpoint_name=(
            f"projects/{project_id}"
            f"/locations/{location}"
            f"/endpoints/{endpoint_id}"
        )
    )

    # The chat model uses prompt + generation parameters.
    instances = [{"prompt": query, "max_tokens": 512, "temperature": 0.2}]
    try:
        response = endpoint.predict(instances=instances)
        raw_output = response.predictions[0]
        if "Output:\n" in raw_output:
            return raw_output.split("Output:\n", 1)[1].strip()
        return raw_output.strip()
    except Exception as e:
        return f"Error querying TxGemma chat endpoint {endpoint_id}: {str(e)}"
