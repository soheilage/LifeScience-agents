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
Pydantic schemas and typed data contracts for radiopharm-target-agent.

Enforces strict provenance, source attribution, and deterministic scoring
contracts according to Section 1 and Section 2 of the implementation plan.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class SourceRef(BaseModel):
    """Reference to the immutable ground-truth source of a claim."""

    kind: Literal[
        "gtex",
        "hpa",
        "uniprot",
        "c2s",
        "ctgov",
        "pubmed",
        "pmc",
        "txgemma",
        "pubchem",
        "local_scrna",
        "manual",
    ]
    identifier: str  # PMID, NCT ID, HPA antibody ID, dataset ID, query hash
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    version: str  # GTEx release, HPA version, CT.gov query date, etc.


class Claim(BaseModel):
    """
    A single typed, sourced scientific observation or measurement.

    Design Principle 1.2: A measured claim without a source cannot be constructed.
    Design Principle 1.4: Missing data is not zero ('not_detected' vs 'not_measured' vs 'no_atlas_for_indication' vs 'not_reported').
    """

    field: str
    value: Any = None  # float, str, bool, dict, list, or None
    unit: str | None = None
    status: Literal[
        "measured",
        "not_detected",
        "not_measured",
        "no_atlas_for_indication",
        "not_reported",
        "unavailable",
    ]
    evidence_tier: Literal[
        "protein_quant",
        "protein_ihc",
        "bulk_rna",
        "sc_rank",
        "literature",
        "absent",
    ]
    delivery_accessibility: Literal[
        "bbb_protected",
        "freely_perfused",
        "actively_reabsorbing",
        "excretory_route",
        "circulating_blood_pool",
        "unspecified",
    ] = "unspecified"
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "high"
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def measured_requires_source(self) -> "Claim":
        """Enforces that any claim marked 'measured' must have at least one SourceRef."""
        if self.status == "measured" and not self.sources:
            raise ValueError(
                f"measured claim '{self.field}' has no source (Design Principle 1.2 violation)"
            )
        return self


class TrialRecord(BaseModel):
    """Structured clinical trial record from ClinicalTrials.gov."""

    nct_id: str
    title: str = "Unspecified Clinical Trial"
    phase: str = "Phase not specified"
    status: str = "Unknown status"
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(
        default_factory=list
    )  # e.g., "therapy", "diagnostic", "ADC", "cell_therapy"
    is_radiopharmaceutical: bool = False
    isotope: str | None = None
    target: str | None = None
    eligibility_criteria: str | None = None
    baseline_imaging_threshold: str | None = None  # e.g., "SUVmax >= 15"
    dose_limiting_toxicity: str | None = None
    absorbed_dose_gy_per_gbq: dict[str, float] | None = None
    species: str = "human"
    sources: list[SourceRef] = Field(default_factory=list)


class LiteratureFinding(BaseModel):
    """Structured literature extraction from PubMed / PMC / MedGemma."""

    pmid: str | None = None
    pmcid: str | None = None
    title: str = "Unspecified Title"
    abstract_excerpt: str = ""
    species: Literal["human", "mouse", "rat", "non_human_primate", "in_vitro", "unspecified"] = "unspecified"
    modality: str | None = None
    dosimetry: dict[str, float] | None = None
    efficacy_endpoints: dict[str, Any] | None = None
    orr: str | None = None
    pfs: str | None = None
    os_endpoint: str | None = None
    is_radiopharmaceutical: bool = False
    isotope: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class SingleCellRoutingMetadata(BaseModel):
    """Single-cell atlas routing decision and audit metadata."""

    selected_atlas_id: str | None = None
    raw_indication: str
    normalized_indication_key: str
    resolution_method: Literal["exact", "synonym", "unmapped"]
    n_cells: int | None = None
    n_patients: int | None = None
    geo_accession: str | None = None
    annotation_source: str | None = None
    publication_doi: str | None = None
    atlas_sha256: str | None = None
    verified_on: str | None = None
    membership_threshold: str | None = None


class RunProvenance(BaseModel):
    """Audit trail and reproducibility stamp for each pipeline run."""

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    gtex_release: str = "v8"
    hpa_version: str = "v23.0"
    c2s_dataset_id: str = "c2s_v1_curated"
    gemini_model_id: str = "gemini-2.5-pro"
    txgemma_chat_endpoint_id: str | None = None
    txgemma_predict_endpoint_id: str | None = None
    medgemma_endpoint_id: str | None = None
    c2s_endpoint_id: str | None = None
    endpoint_health_status: dict[str, str] = Field(default_factory=dict)
    single_cell_routing: SingleCellRoutingMetadata | None = None


class EvidenceBundle(BaseModel):
    """Complete evidence bundle for target assessment across all specialist modules."""

    target: str
    gene_id: str
    indication: str
    isotope_context: Literal[
        "Lu-177", "Ac-225", "Ga-68", "I-131", "Y-90", "Tb-161", "Pb-212"
    ]
    vector_class: Literal["peptide", "small_molecule", "antibody", "nanobody", "unspecified"] = "peptide"
    expression: dict[str, Claim] = Field(default_factory=dict)
    oar_panel: dict[str, Claim] = Field(default_factory=dict)
    single_cell: dict[str, Claim] = Field(default_factory=dict)
    single_cell_routing: SingleCellRoutingMetadata | None = None
    clinical: list[TrialRecord] = Field(default_factory=list)
    literature: list[LiteratureFinding] = Field(default_factory=list)
    target_biology: dict[str, Claim] = Field(default_factory=dict)
    tractability: dict[str, Claim] = Field(default_factory=dict)
    provenance: RunProvenance


class ScoreAxisResult(BaseModel):
    """Detailed score for a single evaluation axis."""

    axis_name: str
    score: float | None = None  # 0.0 to 10.0, or None if withheld
    max_score: float = 10.0
    weight: float
    weighted_score: float | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    status: Literal["scored", "withheld"] = "scored"
    rationale: str
    caveats: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class Scorecard(BaseModel):
    """Auditable, deterministic target scorecard computed by scorer.py."""

    target: str
    gene_id: str
    indication: str
    isotope_context: Literal[
        "Lu-177", "Ac-225", "Ga-68", "I-131", "Y-90", "Tb-161", "Pb-212"
    ]
    vector_class: Literal["peptide", "small_molecule", "antibody", "nanobody", "unspecified"] = "peptide"
    total_score: float | None = None  # 0.0 to 10.0, or None if withheld
    rank: int | None = None
    axes: dict[str, ScoreAxisResult] = Field(default_factory=dict)
    recommendation: Literal[
        "high_priority",
        "moderate_priority",
        "low_priority",
        "fail_membrane_gate",
        "fail_selectivity_gate",
        "withheld_insufficient_evidence",
        "abstain_unrecognized_target",
        "halt_on_contradiction",
    ]
    failure_reasons: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    provenance: RunProvenance
