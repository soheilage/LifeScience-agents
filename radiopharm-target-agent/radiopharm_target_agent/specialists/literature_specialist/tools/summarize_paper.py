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
Tool for structured radiopharmaceutical paper summarization.
Integrates MedGemma Vertex AI endpoint with deterministic rule-based fallback
(Design Principle 1.5: Enrichment models off critical path).
"""

import os
import re
from typing import Any
from dotenv import load_dotenv

from .fetch_articles import (
    DOSE_PATTERN,
    ORR_PATTERN,
    OS_PATTERN,
    PFS_PATTERN,
    detect_species,
)

load_dotenv()


def _rule_based_summary(full_text: str) -> str:
    """Deterministic fallback summarizer when MedGemma endpoint is not active."""
    species = detect_species(full_text)

    dose_matches = DOSE_PATTERN.findall(full_text)
    orr_match = ORR_PATTERN.search(full_text)
    pfs_match = PFS_PATTERN.search(full_text)
    os_match = OS_PATTERN.search(full_text)
    mtd_match = re.search(
        r"(?:MTD|maximum tolerated dose)\s*(?:of|was|is|:)?\s*([^.,;\n]+)",
        full_text,
        re.IGNORECASE,
    )

    lines = [
        "### Structured Radiopharmaceutical Paper Summary (Rule-Based Extraction)",
        f"- **Model Species:** `{species}`",
        f"- **Objective Response Rate (ORR):** {orr_match.group(1) if orr_match else 'Not reported in sampled text'}",
        f"- **Progression-Free Survival (PFS):** {pfs_match.group(1) if pfs_match else 'Not reported'}",
        f"- **Overall Survival (OS):** {os_match.group(1) if os_match else 'Not reported'}",
        f"- **Maximum Tolerated Dose (MTD):** {mtd_match.group(1).strip() if mtd_match else 'Not specified'}",
        f"- **Reported Absorbed Doses (Gy/GBq):** {', '.join(dose_matches[:5]) if dose_matches else 'No quantitative Gy/GBq values detected'}",
        "\n**Text Excerpt:**",
        full_text[:1500] + ("..." if len(full_text) > 1500 else ""),
    ]
    return "\n".join(lines)


def summarize_paper(full_text: str) -> str:
    """
    Analyzes full text of a paper to extract structured radiopharm efficacy,
    dosimetry (Gy/GBq), safety parameters, and species metadata.

    Args:
        full_text: The complete text content of the publication.

    Returns:
        Structured markdown summary containing clinical and dosimetric findings.
    """
    endpoint_id = os.getenv("MEDGEMMA_ENDPOINT_ID")
    project_id = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("CLOUD_ML_PROJECT_ID")
        or os.getenv("PROJECT_ID")
    )
    location = os.getenv("MEDGEMMA_LOCATION", "us-central1")

    # If MedGemma endpoint is not set, use deterministic fallback cleanly
    if not endpoint_id or not project_id:
        return _rule_based_summary(full_text)

    try:
        from google.cloud import aiplatform

        aiplatform.init(project=project_id, location=location)
        endpoint = aiplatform.Endpoint(
            endpoint_name=f"projects/{project_id}/locations/{location}/endpoints/{endpoint_id}"
        )

        prompt = f"""You are an expert radiopharmaceutical literature extraction specialist.
Analyze the following paper text and extract a structured briefing.

Extract precisely:
1. **Model Species:** (human / mouse / rat / in_vitro / non_human_primate)
2. **Key Radiopharmaceutical / Isotope:** (e.g. 177Lu-PSMA-617, 225Ac-DOTATATE, etc.)
3. **Efficacy Metrics:** ORR (%), median PFS, median OS, PSA/target response rates.
4. **Organ Absorbed Doses:** Absorbed dose in Gy/GBq for kidneys, bone marrow, salivary glands, liver, tumor.
5. **Dosimetry Methodology:** (e.g., MIRD schema, planar SPECT/CT, OLINDA/EXM, 3D voxel dosimetry).
6. **Dose-Limiting Toxicities & MTD:** (e.g. xerostomia, thrombocytopenia, nephrotoxicity).

PAPER TEXT:
{full_text[:25000]}
"""
        instances = [{"prompt": prompt, "max_tokens": 1500, "temperature": 0.1}]
        response = endpoint.predict(instances=instances)
        return response.predictions[0]

    except Exception as e:
        fallback = _rule_based_summary(full_text)
        return f"{fallback}\n\n*(Note: MedGemma endpoint call encountered '{e}'; fell back to rule-based extraction)*"
