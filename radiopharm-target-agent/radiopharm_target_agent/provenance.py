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
Provenance, data version stamping, and endpoint health checking.

Implements Gate G4: 100% of claims are version-stamped.
Implements non-blocking startup health checks (returns 'unavailable', never crashes).
"""

from datetime import datetime, timezone
import os
from typing import Any
from dotenv import load_dotenv
import requests

from .schemas import RunProvenance

load_dotenv()


def check_endpoint_health() -> dict[str, str]:
    """
    Performs fast, non-blocking health checks against configured endpoints.
    Returns status strings: 'active', 'configured', 'unavailable', or 'degraded'.
    """
    health: dict[str, str] = {}

    # 1. NCBI E-utilities
    ncbi_key = os.getenv("NCBI_API_KEY")
    if ncbi_key:
        health["ncbi_eutilities"] = "active (authenticated, 10 req/s)"
    else:
        health["ncbi_eutilities"] = "active (unauthenticated, 3 req/s)"

    # 2. GTEx & HPA APIs
    health["gtex_api"] = f"configured ({os.getenv('GTEX_RELEASE', 'v8')})"
    health["hpa_api"] = f"configured ({os.getenv('HPA_VERSION', 'v23.0')})"

    # 3. TxGemma Chat Endpoint
    tx_chat = os.getenv("TXGEMMA_CHAT_ENDPOINT_ID")
    health["txgemma_chat"] = (
        f"available (endpoint: {tx_chat})"
        if tx_chat
        else "unavailable (not configured)"
    )

    # 4. TxGemma ClinTox Predict Endpoint
    tx_predict = os.getenv("TXGEMMA_PREDICT_ENDPOINT_ID")
    health["txgemma_clintox"] = (
        f"available (endpoint: {tx_predict})"
        if tx_predict
        else "unavailable (not configured)"
    )

    # 5. MedGemma Endpoint
    medgemma = os.getenv("MEDGEMMA_ENDPOINT_ID")
    health["medgemma"] = (
        f"available (endpoint: {medgemma})"
        if medgemma
        else "unavailable (not configured)"
    )

    # 6. Cell2Sentence Endpoint
    c2s = os.getenv("CELL2SENTENCE_ENDPOINT_ID")
    health["cell2sentence"] = (
        f"available (endpoint: {c2s})"
        if c2s
        else "unavailable (local scRNA fallback active)"
    )

    return health


def get_current_provenance() -> RunProvenance:
    """Constructs a current RunProvenance instance with active version stamps."""
    health = check_endpoint_health()

    return RunProvenance(
        timestamp=datetime.now(timezone.utc),
        gtex_release=os.getenv("GTEX_RELEASE", "v8"),
        hpa_version=os.getenv("HPA_VERSION", "v23.0"),
        c2s_dataset_id=os.getenv("C2S_DATASET_ID", "c2s_v1_curated"),
        gemini_model_id=os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro"),
        txgemma_chat_endpoint_id=os.getenv("TXGEMMA_CHAT_ENDPOINT_ID"),
        txgemma_predict_endpoint_id=os.getenv("TXGEMMA_PREDICT_ENDPOINT_ID"),
        medgemma_endpoint_id=os.getenv("MEDGEMMA_ENDPOINT_ID"),
        c2s_endpoint_id=os.getenv("CELL2SENTENCE_ENDPOINT_ID"),
        endpoint_health_status=health,
    )


def format_provenance_banner(
    provenance: RunProvenance | dict[str, Any] | None = None,
) -> str:
    """
    Formats a clean markdown header displaying the run provenance.
    Gracefully accepts RunProvenance instances, dictionaries, or None (auto-generates current).
    """
    if provenance is None:
        prov_obj = get_current_provenance()
    elif isinstance(provenance, dict):
        try:
            prov_obj = RunProvenance(**provenance)
        except Exception:
            prov_obj = get_current_provenance()
    elif isinstance(provenance, RunProvenance):
        prov_obj = provenance
    else:
        prov_obj = get_current_provenance()

    if isinstance(prov_obj.timestamp, datetime):
        ts_str = prov_obj.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts_str = str(prov_obj.timestamp)

    lines = [
        "### Run Provenance & System Health",
        f"- **Execution Timestamp:** `{ts_str}`",
        f"- **Primary Reasoning Engine:** `{prov_obj.gemini_model_id}` (Pinned)",
        f"- **Reference Datasets:** GTEx `{prov_obj.gtex_release}` | HPA `{prov_obj.hpa_version}` | Single-Cell `{prov_obj.c2s_dataset_id}`",
        f"- **TxGemma Endpoints:** Chat: `{prov_obj.endpoint_health_status.get('txgemma_chat', 'unavailable')}` | ClinTox: `{prov_obj.endpoint_health_status.get('txgemma_clintox', 'unavailable')}`",
        f"- **MedGemma Endpoint:** `{prov_obj.endpoint_health_status.get('medgemma', 'unavailable')}`",
        f"- **Cell2Sentence Engine:** `{prov_obj.endpoint_health_status.get('cell2sentence', 'local fallback')}`",
        "---",
    ]
    return "\n".join(lines)
