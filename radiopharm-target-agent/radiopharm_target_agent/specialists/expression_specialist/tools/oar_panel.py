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
Organ-at-Risk (OAR) safety panel checklist for radiopharmaceutical target assessment.

Implements Design Principle 1.4: Missing data is not zero ('not_detected' vs 'not_measured').
Specifically, lacrimal_gland and bone_marrow are absent from standard HPA/GTEx profiles
and MUST return 'not_measured', routing to literature as mandatory sub-queries.
"""

from datetime import datetime, timezone
from typing import Any
from radiopharm_target_agent.guards import resolve_gene_symbol
from radiopharm_target_agent.schemas import Claim, SourceRef

# Fixed 9-organ critical panel for targeted radiotherapy
CRITICAL_OAR_PANEL = [
    "kidney_cortex",  # Primary dose-limiting organ (renal tubular reabsorption)
    "bone_marrow",  # Hematological / myelosuppression liability (NOT measured in HPA/GTEx)
    "salivary_gland",  # Xerostomia / dry mouth (dose-limiting for PSMA Ac-225)
    "lacrimal_gland",  # Ocular toxicity / dry eyes (NOT measured in HPA/GTEx)
    "liver",  # Hepatic clearance / metabolic burden
    "spleen",  # Reticuloendothelial uptake
    "gi_tract",  # Mucosal toxicity (small intestine / colon)
    "lung",  # Radiation pneumonitis
    "brain",  # Neurotoxicity / blood-brain barrier integrity
]

# Baseline normal organ expression profiles for control panel targets (GTEx TPM / HPA IHC)
OAR_BASELINE_EXPRESSION_DB: dict[str, dict[str, dict[str, Any]]] = {
    "FOLH1": {
        "kidney_cortex": {
            "value": 45.8,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Proximal tubules)",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 18.4,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Acinar cells)",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.3,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 12.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low to Medium (Duodenum/Jejunum)",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 0.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 1.4,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low (Astrocytes)",
            "tier": "protein_ihc",
        },
    },
    "SSTR2": {
        "kidney_cortex": {
            "value": 3.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low (Tubules)",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 0.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.4,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 14.8,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Lymphoid cells)",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 24.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Enterochromaffin cells)",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 32.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High (Cerebral cortex)",
            "tier": "protein_ihc",
        },
    },
    "STEAP1": {
        "kidney_cortex": {
            "value": 2.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 1.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.8,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.6,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 3.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 1.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
    },
    "TMEFF2": {
        "kidney_cortex": {
            "value": 3.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 2.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 1.0,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 4.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 1.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 48.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High (Cerebral cortex/Hippocampus)",
            "tier": "protein_ihc",
        },
    },
    "DLL3": {
        "kidney_cortex": {
            "value": 0.3,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 0.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 0.4,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 1.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
    },
    "FAP": {
        "kidney_cortex": {
            "value": 0.8,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.3,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.4,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 1.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Low (Stroma only)",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 0.6,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
    },
    "GAPDH": {
        "kidney_cortex": {
            "value": 2450.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "salivary_gland": {
            "value": 1890.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "liver": {
            "value": 3100.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "spleen": {
            "value": 1950.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "gi_tract": {
            "value": 2200.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "lung": {
            "value": 2800.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
        "brain": {
            "value": 1650.0,
            "unit": "TPM",
            "status": "measured",
            "ihc": "High",
            "tier": "bulk_rna",
        },
    },
    "MSLN": {
        "kidney_cortex": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 0.1,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 0.4,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Low (Peritoneum lining)",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 1.8,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Pleural mesothelial cells)",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 0.0,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
    },
    "ERBB2": {
        "kidney_cortex": {
            "value": 28.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low to Medium (Tubules)",
            "tier": "protein_ihc",
        },
        "salivary_gland": {
            "value": 14.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "liver": {
            "value": 8.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
        "spleen": {
            "value": 1.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Not detected",
            "tier": "protein_ihc",
        },
        "gi_tract": {
            "value": 35.8,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Gastrointestinal mucosa)",
            "tier": "protein_ihc",
        },
        "lung": {
            "value": 22.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low (Bronchial epithelium)",
            "tier": "protein_ihc",
        },
        "brain": {
            "value": 3.4,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "protein_ihc",
        },
    },
    "MKI67": {
        "kidney_cortex": {
            "value": 0.8,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Negative",
            "tier": "bulk_rna",
        },
        "salivary_gland": {
            "value": 0.6,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Negative",
            "tier": "bulk_rna",
        },
        "liver": {
            "value": 0.4,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Negative",
            "tier": "bulk_rna",
        },
        "spleen": {
            "value": 8.4,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low (Germinal center blasts)",
            "tier": "bulk_rna",
        },
        "gi_tract": {
            "value": 14.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Medium (Crypt progenitor cells)",
            "tier": "bulk_rna",
        },
        "lung": {
            "value": 0.5,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Negative",
            "tier": "bulk_rna",
        },
        "brain": {
            "value": 0.2,
            "unit": "TPM",
            "status": "not_detected",
            "ihc": "Negative",
            "tier": "bulk_rna",
        },
    },
    "TP53": {
        "kidney_cortex": {
            "value": 18.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "salivary_gland": {
            "value": 15.4,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "liver": {
            "value": 12.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "spleen": {
            "value": 22.5,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "gi_tract": {
            "value": 25.1,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "lung": {
            "value": 19.8,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
        "brain": {
            "value": 14.2,
            "unit": "TPM",
            "status": "measured",
            "ihc": "Low",
            "tier": "bulk_rna",
        },
    },
}


def build_oar_panel(target_symbol: str) -> dict[str, Any]:
    """
    Evaluates the 9 critical radiation Organ-at-Risk (OAR) safety checklist for a target.

    Design Principle 1.4 & Phase 2 Exit Requirement:
    - lacrimal_gland and bone_marrow MUST return 'not_measured', never 'not_detected' or '0'.
    - Mandatory literature sub-queries are generated for any unmeasured organs.

    Args:
        target_symbol: Gene symbol or common alias.

    Returns:
        Dictionary of organ claims and recommended literature sub-queries.
    """
    resolved = resolve_gene_symbol(target_symbol)
    if resolved.get("status") == "abstain":
        return {
            "status": "abstain",
            "target": target_symbol,
            "reason": resolved.get("reason"),
            "claims": {},
            "mandatory_literature_subqueries": [],
        }

    canonical = resolved.get("canonical_symbol", target_symbol)
    target_data = OAR_BASELINE_EXPRESSION_DB.get(canonical, {})

    claims: dict[str, Claim] = {}
    mandatory_subqueries: list[str] = []

    hpa_source = SourceRef(
        kind="hpa",
        identifier=f"{canonical}_HPA_Normal_IHC",
        retrieved_at=datetime.now(timezone.utc),
        version="v23.0",
    )
    gtex_source = SourceRef(
        kind="gtex",
        identifier=f"{canonical}_GTEx_v8_Median_TPM",
        retrieved_at=datetime.now(timezone.utc),
        version="v8",
    )

    for organ in CRITICAL_OAR_PANEL:
        # HARD REQUIREMENT: lacrimal_gland and bone_marrow are absent from standard HPA/GTEx
        if organ in ["lacrimal_gland", "bone_marrow"]:
            claims[organ] = Claim(
                field=f"oar_{organ}",
                value=None,
                unit=None,
                status="not_measured",
                evidence_tier="absent",
                sources=[],
                confidence="high",
                caveats=[
                    f"Tissue '{organ}' is not represented in standard HPA Tissue Atlas IHC or GTEx bulk RNA profiles. "
                    "Must be evaluated via clinical trial biodistribution or literature."
                ],
            )
            mandatory_subqueries.append(
                f"{canonical} {organ.replace('_', ' ')} radiotracer uptake biodistribution dosimetry"
            )
            continue

        # Organs present in database
        organ_info = target_data.get(organ)
        if organ_info:
            status = organ_info["status"]
            val = organ_info["value"]
            tier = organ_info["tier"]
            ihc_desc = organ_info.get("ihc", "IHC evaluated")

            sources = [hpa_source, gtex_source]
            claims[organ] = Claim(
                field=f"oar_{organ}",
                value=val,
                unit="TPM",
                status=status,
                evidence_tier=tier,
                sources=sources,
                confidence="high",
                caveats=[
                    f"Normal IHC staining: {ihc_desc}."
                    if status != "not_detected"
                    else f"Normal IHC staining: Negative / not detected."
                ],
            )
        else:
            # Fallback for targets outside curated DB
            claims[organ] = Claim(
                field=f"oar_{organ}",
                value=None,
                unit="TPM",
                status="not_measured",
                evidence_tier="absent",
                sources=[],
                confidence="low",
                caveats=[
                    f"Baseline expression data for '{organ}' not found in database."
                ],
            )
            mandatory_subqueries.append(
                f"{canonical} {organ.replace('_', ' ')} expression"
            )

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "claims": claims,
        "mandatory_literature_subqueries": mandatory_subqueries,
    }
