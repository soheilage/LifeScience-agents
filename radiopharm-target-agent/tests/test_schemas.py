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
Unit tests for schemas.py — validating Design Principles 1.1, 1.2, 1.4.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from radiopharm_target_agent.schemas import (
    Claim,
    EvidenceBundle,
    LiteratureFinding,
    RunProvenance,
    ScoreAxisResult,
    Scorecard,
    SourceRef,
    TrialRecord,
)


def test_claim_measured_without_source_raises_validation_error():
    """
    Phase 0 Exit Gate Requirement:
    A Claim with status='measured' and empty sources list MUST raise a ValidationError.
    """
    with pytest.raises(ValidationError) as exc_info:
        Claim(
            field="gtex_kidney_cortex_tpm",
            value=142.5,
            unit="TPM",
            status="measured",
            evidence_tier="bulk_rna",
            sources=[],  # Violates Design Principle 1.2
            confidence="high",
        )
    assert "has no source" in str(exc_info.value)


def test_claim_measured_with_valid_source_succeeds():
    """A Claim with status='measured' and a valid SourceRef must validate cleanly."""
    ref = SourceRef(
        kind="gtex",
        identifier="GTEx_Analysis_v8_RNASeQCv1.1.9_gene_median_tpm",
        retrieved_at=datetime.now(timezone.utc),
        version="v8",
    )
    claim = Claim(
        field="gtex_kidney_cortex_tpm",
        value=142.5,
        unit="TPM",
        status="measured",
        evidence_tier="bulk_rna",
        sources=[ref],
        confidence="high",
        caveats=["Bulk tissue averages all cellular compartments."],
    )
    assert claim.status == "measured"
    assert claim.value == 142.5
    assert len(claim.sources) == 1
    assert claim.sources[0].kind == "gtex"


def test_claim_not_measured_allows_empty_sources():
    """A Claim with status='not_measured' is valid with empty sources (Design Principle 1.4)."""
    claim = Claim(
        field="hpa_lacrimal_gland_ihc",
        value=None,
        status="not_measured",
        evidence_tier="absent",
        sources=[],
        confidence="high",
        caveats=["Lacrimal gland tissue not sampled in HPA Tissue Atlas."],
    )
    assert claim.status == "not_measured"
    assert claim.value is None


def test_claim_not_detected_with_source_succeeds():
    """A Claim with status='not_detected' indicates target was tested but absent."""
    ref = SourceRef(
        kind="hpa",
        identifier="HPA001234",
        retrieved_at=datetime.now(timezone.utc),
        version="v23.0",
    )
    claim = Claim(
        field="hpa_cerebral_cortex_ihc",
        value="Negative",
        status="not_detected",
        evidence_tier="protein_ihc",
        sources=[ref],
        confidence="high",
    )
    assert claim.status == "not_detected"
    assert claim.value == "Negative"


def test_evidence_bundle_instantiation():
    """Tests constructing a complete typed EvidenceBundle."""
    ref = SourceRef(
        kind="uniprot",
        identifier="Q04656",
        retrieved_at=datetime.now(timezone.utc),
        version="2026_01",
    )
    prov = RunProvenance(
        gemini_model_id="gemini-2.5-pro",
        gtex_release="v8",
        hpa_version="v23.0",
    )
    bundle = EvidenceBundle(
        target="FOLH1",
        gene_id="ENSG00000086205",
        indication="Prostate Adenocarcinoma",
        isotope_context="Lu-177",
        expression={
            "tumour_selectivity_ratio": Claim(
                field="tumour_selectivity_ratio",
                value=24.5,
                unit="T/N_ratio",
                status="measured",
                evidence_tier="bulk_rna",
                sources=[ref],
                confidence="high",
            )
        },
        oar_panel={
            "kidney_cortex": Claim(
                field="kidney_cortex",
                value=45.2,
                unit="TPM",
                status="measured",
                evidence_tier="bulk_rna",
                sources=[ref],
                confidence="high",
            ),
            "lacrimal_gland": Claim(
                field="lacrimal_gland",
                value=None,
                status="not_measured",
                evidence_tier="absent",
                sources=[],
                confidence="medium",
            ),
        },
        single_cell={},
        clinical=[],
        literature=[],
        target_biology={},
        tractability={},
        provenance=prov,
    )
    assert bundle.target == "FOLH1"
    assert bundle.isotope_context == "Lu-177"
    assert "kidney_cortex" in bundle.oar_panel
    assert bundle.oar_panel["lacrimal_gland"].status == "not_measured"


def test_scorecard_structure():
    """Tests constructing a deterministic Scorecard."""
    prov = RunProvenance()
    scorecard = Scorecard(
        target="FOLH1",
        gene_id="ENSG00000086205",
        indication="Prostate Adenocarcinoma",
        isotope_context="Lu-177",
        total_score=8.45,
        rank=1,
        axes={
            "tumour_selectivity": ScoreAxisResult(
                axis_name="tumour_selectivity",
                score=9.0,
                weight=0.20,
                weighted_score=1.80,
                confidence="high",
                status="scored",
                rationale="High T/N ratio confirmed across HPA Pathology Atlas.",
                sources=[
                    SourceRef(
                        kind="hpa",
                        identifier="FOLH1_Pathology",
                        version="v23.0",
                    )
                ],
            )
        },
        recommendation="high_priority",
        failure_reasons=[],
        caveats=["Salivary gland uptake requires monitoring."],
        provenance=prov,
    )
    assert scorecard.total_score == 8.45
    assert scorecard.recommendation == "high_priority"
    assert "tumour_selectivity" in scorecard.axes


def test_sme_signoff_schema_guard_rejects_empty_reviewer():
    """
    R4 Schema Guard Test:
    Any sme_signoff block with an empty or whitespace reviewer_name raises a ValidationError / ValueError
    and refuses to validate.
    """
    from radiopharm_target_agent.schemas import SMESignOffRecord, validate_sme_signoff_block

    # 1. Empty reviewer name raises ValidationError
    with pytest.raises(ValidationError) as exc1:
        SMESignOffRecord(
            reviewer_name="",  # Invalid: empty string
            reviewer_role="Nuclear Medicine Specialist",
            reviewer_affiliation="Hospital",
            date="2026-08-21",
            claims_reviewed=["BBB protection"],
            verdict="confirmed",
        )
    assert "cannot be empty or whitespace" in str(exc1.value)

    # 2. Whitespace-only reviewer name raises ValidationError
    with pytest.raises(ValidationError) as exc2:
        SMESignOffRecord(
            reviewer_name="   ",
            reviewer_role="Specialist",
            reviewer_affiliation="Clinic",
            date="2026-08-21",
            claims_reviewed=["Renal tubular reabsorption"],
            verdict="confirmed",
        )
    assert "cannot be empty or whitespace" in str(exc2.value)

    # 3. Empty claims list raises ValidationError
    with pytest.raises(ValidationError) as exc3:
        SMESignOffRecord(
            reviewer_name="Dr. Jane Doe",
            reviewer_role="Specialist",
            reviewer_affiliation="Clinic",
            date="2026-08-21",
            claims_reviewed=[],  # Invalid: empty list
            verdict="confirmed",
        )
    assert "must list at least one claim" in str(exc3.value)

    # 4. Valid signed-off block validates cleanly
    valid_record = validate_sme_signoff_block({
        "reviewer_name": "Dr. Alex Mercer, PharmD",
        "reviewer_role": "Radiopharmacy Lead",
        "reviewer_affiliation": "European Association of Nuclear Medicine (EANM)",
        "date": "2026-08-21",
        "claims_reviewed": ["BBB protection", "Renal reabsorption"],
        "verdict": "confirmed_with_conditions",
    })
    assert valid_record.reviewer_name == "Dr. Alex Mercer, PharmD"
    assert valid_record.verdict == "confirmed_with_conditions"

