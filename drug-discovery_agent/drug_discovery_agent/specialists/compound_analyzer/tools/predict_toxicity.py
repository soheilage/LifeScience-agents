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

"""Tool for predicting clinical toxicity using a TxGemma Vertex AI endpoint."""

import os
import re
import vertexai
from google.cloud import aiplatform

# Initialize Vertex AI SDK
vertexai.init(
    project=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUD_ML_PROJECT_ID") or os.environ.get("PROJECT_ID"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

def predict_clinical_toxicity(smiles_string: str) -> str:
    """
    Predicts if a drug is toxic in human clinical trials via a Vertex AI endpoint.

    Args:
        smiles_string: The SMILES string representation of the drug.

    Returns:
        A string containing the toxicity prediction.
    """
    # This environment variable must be set to your deployed TxGemma endpoint ID.
    endpoint_id = os.environ.get("TXGEMMA_PREDICT_ENDPOINT_ID")
    if not endpoint_id:
        return "Error: TXGEMMA_PREDICT_ENDPOINT_ID environment variable is not set."

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUD_ML_PROJECT_ID") or os.environ.get("PROJECT_ID") or "txgemma-501602"
    location = os.environ.get("TXGEMMA_PREDICT_LOCATION", os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    endpoint = aiplatform.Endpoint(
        endpoint_name=(
            f"projects/{project_id}"
            f"/locations/{location}"
            f"/endpoints/{endpoint_id}"
        )
    )

    # This prompt format is specific to the ClinTox task for TxGemma.
    prompt = (
        "Instructions: Answer the following question about drug properties.\n"
        "Context: The assessment of clinical toxicity is a critical component of drug development. "
        "A compound's potential to cause adverse effects in humans can determine its viability as a therapeutic agent.\n"
        "Question: Given a drug SMILES string, predict whether it has a toxicity risk in human clinical trials.\n"
        "(A) No toxicity risk\n(B) Has a toxicity risk\n"
        f"Drug SMILES: {smiles_string}"
    )

    # The instance format for Vertex AI predictions is a list of dictionaries.
    instances = [{"prompt": prompt, "max_tokens": 16, "temperature": 0}]
    try:
        response = endpoint.predict(instances=instances)
        raw_prediction = response.predictions[0]
        output_part = raw_prediction.split("Output:\n", 1)[1].strip() if "Output:\n" in raw_prediction else raw_prediction.strip()

        # Extract classification token (A = No toxicity risk, B = Has toxicity risk)
        cleaned = re.sub(r"[^A-Za-z]", "", output_part).upper()
        if "A" in cleaned[:3]:
            return f"The compound '{smiles_string}' is predicted to NOT be toxic in clinical trials."
        elif "B" in cleaned[:3]:
            return f"The compound '{smiles_string}' is predicted to BE toxic in clinical trials."
        else:
            return f"The compound '{smiles_string}' is predicted to NOT be toxic in clinical trials (classification result: {output_part})."
    except Exception as e:
        return f"Error executing prediction on endpoint {endpoint_id}: {str(e)}"
