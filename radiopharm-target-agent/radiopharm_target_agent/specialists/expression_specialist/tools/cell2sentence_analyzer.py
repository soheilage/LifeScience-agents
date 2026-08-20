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
Single-Cell Transcriptomics & Cell2Sentence (C2S) Deconvolution Tool.

Design Principles & Remediation:
- Action 1: Ontology-driven, fail-closed routing via atlas_registry.yaml (no substring matching).
- Action 2: Split status vocabulary ('not_detected' vs 'no_atlas_for_indication').
- Action 3: Surface full routing decision in output and provenance.
- Action 6: Documented and logged membership threshold.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any
import yaml

from radiopharm_target_agent.guards import resolve_gene_symbol
from radiopharm_target_agent.schemas import (
    Claim,
    SingleCellRoutingMetadata,
    SourceRef,
)

REFERENCE_DATE = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

REGISTRY_PATH = Path(__file__).parent.parent / "atlas_registry.yaml"


def load_atlas_registry() -> dict[str, Any]:
    """Loads the single-cell atlas registry and indication ontology."""
    if not REGISTRY_PATH.exists():
        return {"atlases": [], "indication_ontology": {}, "membership_threshold": {}}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize_indication_string(raw: str) -> str:
    """
    Strict normalisation: lowercase, strip punctuation, collapse whitespace.
    """
    if not raw:
        return ""
    # Strip all non-alphanumeric characters (except whitespace)
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", raw.lower())
    # Collapse multiple whitespaces
    return " ".join(cleaned.split())


def route_indication_to_atlas(
    raw_indication: str,
    registry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, SingleCellRoutingMetadata]:
    """
    Resolves an indication string to a registered atlas using strict curated ontology.

    Resolution order:
    1. Exact normalized match against canonical ontology keys.
    2. Exact match against curated synonyms.
    3. Fail closed -> returns (None, metadata with 'unmapped').

    STRICT: No substring matching. No fuzzy matching.
    """
    if registry is None:
        registry = load_atlas_registry()

    ontology = registry.get("indication_ontology", {})
    atlases = {a["id"]: a for a in registry.get("atlases", [])}
    threshold_info = registry.get("membership_threshold", {})
    thresh_desc = threshold_info.get(
        "description", "min count > 0 in >= 1.0% compartment cells"
    )

    norm_str = normalize_indication_string(raw_indication)
    norm_key = norm_str.replace(" ", "_")

    selected_atlas_id: str | None = None
    resolution_method: str = "unmapped"

    # Step 1: Exact canonical match
    if norm_key in ontology:
        selected_atlas_id = ontology[norm_key].get("atlas")
        resolution_method = "exact"
    elif norm_str in ontology:
        selected_atlas_id = ontology[norm_str].get("atlas")
        resolution_method = "exact"
    else:
        # Step 2: Synonym table match
        for can_key, entry in ontology.items():
            synonyms = entry.get("synonyms", [])
            norm_synonyms = [
                normalize_indication_string(str(s)) for s in synonyms
            ]
            norm_syn_keys = [s.replace(" ", "_") for s in norm_synonyms]
            if norm_str in norm_synonyms or norm_key in norm_syn_keys:
                selected_atlas_id = entry.get("atlas")
                resolution_method = "synonym"
                break

    # Step 3: Fail closed if unmapped
    if not selected_atlas_id or selected_atlas_id not in atlases:
        meta = SingleCellRoutingMetadata(
            selected_atlas_id=None,
            raw_indication=raw_indication,
            normalized_indication_key=norm_key,
            resolution_method="unmapped",
            membership_threshold=thresh_desc,
        )
        return None, meta

    atlas_data = atlases[selected_atlas_id]
    meta = SingleCellRoutingMetadata(
        selected_atlas_id=selected_atlas_id,
        raw_indication=raw_indication,
        normalized_indication_key=norm_key,
        resolution_method=resolution_method,  # type: ignore
        n_cells=atlas_data.get("n_cells"),
        n_patients=atlas_data.get("n_patients"),
        annotation_source=atlas_data.get("annotation_source"),
        publication_doi=atlas_data.get("publication_doi"),
        verified_on=str(atlas_data.get("verified_on")),
        membership_threshold=thresh_desc,
    )
    return atlas_data, meta


def analyze_single_cell_target(
    target_symbol: str, indication: str | None = None
) -> dict[str, Any]:
    """
    Validates single-cell target expression across tumour vs stroma vs immune compartments.

    Applies fail-closed ontology routing and strict membership gating:
    - If unmapped indication: status='no_atlas_for_indication' (withheld, non-penalizing).
    - If atlas present but gene below threshold: status='not_detected'.
    - If gene present: status='measured' with compartment deconvolution & dispersion.
    """
    resolved = resolve_gene_symbol(target_symbol)
    if resolved.get("status") == "abstain":
        return {
            "status": "abstain",
            "target": target_symbol,
            "reason": resolved.get("reason"),
            "claims": {},
            "routing": None,
        }

    canonical = resolved.get("canonical_symbol", target_symbol)
    indication_str = indication or "prostate_adenocarcinoma"

    registry = load_atlas_registry()
    atlas_info, routing_meta = route_indication_to_atlas(
        indication_str, registry
    )

    # 1. Unmapped indication -> Fail closed
    if not atlas_info:
        claim_unmapped = Claim(
            field="single_cell_specificity",
            value=None,
            status="no_atlas_for_indication",
            evidence_tier="absent",
            sources=[],
            confidence="high",
            caveats=[
                f"No single-cell atlas registered for indication '{indication_str}' (Normalized key: '{routing_meta.normalized_indication_key}'). "
                "Single-cell evidence withheld; axis will not be penalized."
            ],
        )
        return {
            "status": "no_atlas_for_indication",
            "target": target_symbol,
            "canonical_symbol": canonical,
            "indication": indication_str,
            "dominant_compartment": None,
            "percent_positive_malignant_cells": None,
            "dispersion": None,
            "bimodality": None,
            "summary": f"Single-cell evidence unavailable — no atlas registered for indication '{indication_str}'.",
            "claims": {"single_cell_specificity": claim_unmapped},
            "routing": routing_meta.model_dump(),
        }

    atlas_id = atlas_info["id"]
    doi = atlas_info.get("publication_doi", "DOI_Unavailable")
    source_ref = SourceRef(
        kind="c2s",
        identifier=atlas_id,
        retrieved_at=REFERENCE_DATE,
        version=f"DOI:{doi}",
    )

    gene_membership = atlas_info.get("gene_membership", {})
    gene_data = gene_membership.get(canonical)

    # 2. Atlas mapped, but gene absent / below membership threshold
    if not gene_data:
        claim_absent = Claim(
            field="single_cell_specificity",
            value="not_detected",
            status="not_detected",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
            caveats=[
                f"Gene '{canonical}' was not detected above threshold ({routing_meta.membership_threshold}) in atlas '{atlas_id}'. "
                "Genuinely absent or below single-cell detection threshold in malignant/stromal compartments."
            ],
        )
        return {
            "status": "not_detected",
            "target": target_symbol,
            "canonical_symbol": canonical,
            "dataset_id": atlas_id,
            "dominant_compartment": None,
            "percent_positive_malignant_cells": 0.0,
            "dispersion": 0.0,
            "bimodality": False,
            "summary": f"Gene '{canonical}' was queried in atlas '{atlas_id}' and not detected above threshold.",
            "claims": {"single_cell_specificity": claim_absent},
            "routing": routing_meta.model_dump(),
        }

    # 3. Target present in atlas -> extract measured compartment and heterogeneity metrics
    dominant_comp = gene_data["dominant_compartment"]
    pct_pos_mal = gene_data.get("percent_positive_malignant_cells", 0.0)
    disp = gene_data.get("expression_dispersion", 0.0)
    bimodal = gene_data.get("bimodality", False)

    claims = {
        "sc_dominant_compartment": Claim(
            field="sc_dominant_compartment",
            value=dominant_comp,
            status="measured",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
            caveats=[gene_data["summary"]],
        ),
        "sc_percent_positive_malignant": Claim(
            field="sc_percent_positive_malignant",
            value=pct_pos_mal,
            unit="percent",
            status="measured",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
        ),
        "sc_expression_dispersion": Claim(
            field="sc_expression_dispersion",
            value=disp,
            unit="gini_dispersion",
            status="measured",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
        ),
        "sc_bimodality": Claim(
            field="sc_bimodality",
            value=bimodal,
            status="measured",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
        ),
        "single_cell_specificity": Claim(
            field="single_cell_specificity",
            value=dominant_comp,
            status="measured",
            evidence_tier="sc_rank",
            sources=[source_ref],
            confidence="high",
            caveats=[gene_data["summary"]],
        ),
    }

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "dataset_id": atlas_id,
        "dominant_compartment": dominant_comp,
        "percent_positive_malignant_cells": pct_pos_mal,
        "dispersion": disp,
        "bimodality": bimodal,
        "summary": gene_data["summary"],
        "claims": claims,
        "routing": routing_meta.model_dump(),
    }
