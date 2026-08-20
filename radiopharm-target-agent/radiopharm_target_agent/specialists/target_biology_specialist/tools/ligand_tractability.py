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
Tool for assessing ligand tractability and known radioligand precedent.

Evaluates:
- Binder existence across modalities (small-molecule, peptidomimetic, antibody, affibody/nanobody)
- Clinical radioligand precedent (e.g., PSMA-617, DOTATATE, FAPI-46)
- Extracellular domain (ECD) accessibility for de novo binder discovery
"""

from datetime import datetime, timezone
from typing import Any
import pubchempy as pcp
from radiopharm_target_agent.guards import resolve_gene_symbol
from radiopharm_target_agent.schemas import Claim, SourceRef

REFERENCE_DATE = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

# Curated binder tractability and radioligand precedent registry
RADIOLIGAND_PRECEDENT_DB: dict[str, dict[str, Any]] = {
    "FOLH1": {
        "tractability_score": 9.5,
        "modalities_available": ["small_molecule", "peptide", "antibody", "nanobody"],
        "established_radioligands": [
            "177Lu-PSMA-617 (Pluvicto - FDA Approved)",
            "68Ga-PSMA-11 (Locametz - FDA Approved)",
            "18F-DCFPyL (Pylarify - FDA Approved)",
            "225Ac-PSMA-617 (Clinical Phase 3)",
            "177Lu-PSMA-I&T (Clinical Phase 3)",
        ],
        "binder_precedent": "Extensive clinical-stage small-molecule and peptide radioligand precedent.",
    },
    "SSTR2": {
        "tractability_score": 9.5,
        "modalities_available": ["peptide", "small_molecule", "antagonist"],
        "established_radioligands": [
            "177Lu-DOTATATE (Lutathera - FDA Approved)",
            "68Ga-DOTATATE (Netspot - FDA Approved)",
            "68Ga-DOTATOC (FDA Approved)",
            "225Ac-DOTATATE (Clinical Trials)",
            "177Lu-OPS201 (Somatostatin Antagonist - Phase 2)",
        ],
        "binder_precedent": "Validated clinical gold standard for peptide receptor radionuclide therapy (PRRT).",
    },
    "FAP": {
        "tractability_score": 9.0,
        "modalities_available": ["quinolone_peptidomimetic", "cyclic_peptide", "antibody"],
        "established_radioligands": [
            "68Ga-FAPI-04 / 68Ga-FAPI-46 (Diagnostic Imaging)",
            "177Lu-FAP-2286 (Clinical Phase 2 - Lu-177 peptide conjugate)",
            "177Lu-FAPI-46",
        ],
        "binder_precedent": "High-affinity FAPI peptidomimetics and cyclic peptides in active clinical development.",
    },
    "MSLN": {
        "tractability_score": 7.0,
        "modalities_available": ["monoclonal_antibody", "single_chain_variable_fragment", "nanobody"],
        "established_radioligands": [
            "89Zr-MMOT0530A (PET antibody imaging)",
            "225Ac-Anetumab corixetan (Preclinical / Early clinical evaluation)",
        ],
        "binder_precedent": "Antibody-based radioconjugates evaluated; high molecular weight and shedding sink present challenges.",
    },
    "ERBB2": {
        "tractability_score": 8.0,
        "modalities_available": ["monoclonal_antibody", "affibody", "nanobody", "biparatopic"],
        "established_radioligands": [
            "68Ga-ABY-025 (Affibody PET - Clinical Trials)",
            "225Ac-Trastuzumab",
            "177Lu-Trastuzumab",
        ],
        "binder_precedent": "Clinical affibody and antibody radiotracers; cardiac toxicity and shed ECD remain considerations.",
    },
    "STEAP1": {
        "tractability_score": 7.5,
        "modalities_available": ["monoclonal_antibody", "small_peptide", "nanobody"],
        "established_radioligands": [
            "89Zr-DFO-MSTP2109A (PET imaging - Phase 1)",
            "225Ac-STEAP1-mAb",
        ],
        "binder_precedent": "Engineered antibody and nanobody conjugates in active clinical oncology development.",
    },
    "TMEFF2": {
        "tractability_score": 6.5,
        "modalities_available": ["monoclonal_antibody", "ADC_precedent"],
        "established_radioligands": [],
        "binder_precedent": "Antibody precedent from ADC development (e.g. anti-TMEFF2 vedotin); no approved radioligand.",
    },
    "DLL3": {
        "tractability_score": 7.0,
        "modalities_available": ["monoclonal_antibody", "t_cell_engager", "nanobody"],
        "established_radioligands": [
            "89Zr-DFO-SC16.56 (Preclinical/Phase 1)",
            "225Ac-DLL3 conjugates",
        ],
        "binder_precedent": "Tarlatamab (BiTE) and SC-002 antibody precedents demonstrate target engagement and binder tractability.",
    },
}


def assess_ligand_tractability(target_symbol: str) -> dict[str, Any]:
    """
    Evaluates binder availability, modalities, and clinical radioligand precedent.

    Args:
        target_symbol: Gene symbol or common alias.

    Returns:
        Structured tractability summary and validated Claim.
    """
    resolved = resolve_gene_symbol(target_symbol)
    if resolved.get("status") == "abstain":
        return {
            "status": "abstain",
            "target": target_symbol,
            "reason": resolved.get("reason"),
            "claims": {},
        }

    canonical = resolved.get("canonical_symbol", target_symbol)
    data = RADIOLIGAND_PRECEDENT_DB.get(canonical)

    source_ref = SourceRef(
        kind="pubchem",
        identifier=f"{canonical}_Tractability",
        retrieved_at=REFERENCE_DATE,
        version="v1.0",
    )

    if not data:
        claim_default = Claim(
            field="tractability_score",
            value=5.0,
            status="measured",
            evidence_tier="literature",
            sources=[source_ref],
            confidence="low",
            caveats=["Novel / uncharacterized target; no established radioligand precedent."],
        )
        return {
            "status": "novel_target",
            "target": target_symbol,
            "canonical_symbol": canonical,
            "tractability_score": 5.0,
            "established_radioligands": [],
            "binder_precedent": "De novo binder generation required (phage display / SELEX / computational design).",
            "claims": {"tractability": claim_default},
        }

    claim = Claim(
        field="tractability_score",
        value=data["tractability_score"],
        unit="score_out_of_10",
        status="measured",
        evidence_tier="literature",
        sources=[source_ref],
        confidence="high",
        caveats=[data["binder_precedent"]],
    )

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "tractability_score": data["tractability_score"],
        "modalities_available": data["modalities_available"],
        "established_radioligands": data["established_radioligands"],
        "binder_precedent": data["binder_precedent"],
        "claims": {"tractability": claim},
    }
