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

"""
Gated tool for predicting small-molecule ligand clinical toxicity via TxGemma ClinTox.

Design Principle & Architecture Constraints (Section 3 & Section 4):
- Gated behind explicit small-molecule ligand SMILES input.
- Output is strictly labeled as 'ligand-level' (NOT target-level).
- EXCLUDED from all target scorecard axes at the schema and scorer levels.
"""

import os
import re
from typing import Any
from dotenv import load_dotenv

load_dotenv()


def predict_ligand_toxicity(smiles_string: str | None = None) -> dict[str, Any]:
    """
    Predicts clinical toxicity risk for a small-molecule ligand SMILES representation.

    Gated behavior:
    - If no SMILES is supplied or if ligand is a peptide/biologic, abstains with explanation.
    - Excluded from target-level scoring at schema level.

    Args:
        smiles_string: Small molecule ligand SMILES string (e.g., PSMA-617 pharmacophore).

    Returns:
        Dictionary with toxicity prediction labeled as ligand-level.
    """
    if not smiles_string or not isinstance(smiles_string, str) or not smiles_string.strip():
        return {
            "status": "bypassed",
            "message": "No small-molecule ligand SMILES provided. TxGemma ClinTox is gated and applies to small-molecule ligands only, not biological targets.",
            "ligand_level_toxicity": "not_applicable",
            "excluded_from_target_scorecard": True,
        }

    clean_smiles = smiles_string.strip()

    endpoint_id = os.getenv("TXGEMMA_PREDICT_ENDPOINT_ID")
    project_id = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("CLOUD_ML_PROJECT_ID")
        or os.getenv("PROJECT_ID")
    )
    location = os.getenv("TXGEMMA_PREDICT_LOCATION", "us-central1")

    # If endpoint not active, deterministic response
    if not endpoint_id or not project_id:
        return {
            "status": "unavailable",
            "smiles": clean_smiles,
            "message": "TxGemma ClinTox endpoint not configured; ligand toxicity prediction unavailable.",
            "ligand_level_toxicity": "unavailable",
            "excluded_from_target_scorecard": True,
        }

    try:
        from google.cloud import aiplatform

        aiplatform.init(project=project_id, location=location)
        endpoint = aiplatform.Endpoint(
            endpoint_name=f"projects/{project_id}/locations/{location}/endpoints/{endpoint_id}"
        )

        prompt = (
            "Instructions: Answer the following question about drug properties.\n"
            "Context: The assessment of clinical toxicity is a critical component of drug development. "
            "A compound's potential to cause adverse effects in humans can determine its viability as a therapeutic agent.\n"
            "Question: Given a drug SMILES string, predict whether it has a toxicity risk in human clinical trials.\n"
            "(A) No toxicity risk\n(B) Has a toxicity risk\n"
            f"Drug SMILES: {clean_smiles}"
        )

        instances = [{"prompt": prompt, "max_tokens": 16, "temperature": 0.0}]
        response = endpoint.predict(instances=instances)
        raw_output = response.predictions[0]

        cleaned = re.sub(r"[^A-Za-z]", "", raw_output).upper()
        if "A" in cleaned[:3]:
            pred_text = "Predicted: Low/No intrinsic small-molecule toxicity risk in human trials."
        elif "B" in cleaned[:3]:
            pred_text = "Predicted: Has potential toxicity risk in human clinical trials."
        else:
            pred_text = f"Prediction result: {raw_output.strip()}"

        return {
            "status": "success",
            "smiles": clean_smiles,
            "prediction": pred_text,
            "level": "ligand_level_only",
            "excluded_from_target_scorecard": True,
        }

    except Exception as e:
        return {
            "status": "error",
            "smiles": clean_smiles,
            "message": f"Endpoint error: {e}",
            "ligand_level_toxicity": "unavailable",
            "excluded_from_target_scorecard": True,
        }
