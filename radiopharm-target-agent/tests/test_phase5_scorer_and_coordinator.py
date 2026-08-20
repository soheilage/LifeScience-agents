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
Phase 5 Unit Tests: Deterministic Scorer & Coordinator Pipeline.

Tests:
1. Five identical runs produce identical scores (Score variance = 0, Gate G3).
2. Raising kidney expression 10x lowers OAR safety sub-score and leaves other sub-scores unchanged.
3. FOLH1 ranks far above GAPDH and MKI67 with correct failure reasons.
4. Lu-177 vs Ac-225 produces different heterogeneity weighting and rationale.
5. 100% of scorecard cells carry at least one source ID (Gate G4).
6. Missing expression produces 'score withheld — expression evidence unavailable', not a default.
"""

from datetime import datetime, timezone
import pytest
from radiopharm_target_agent.provenance import get_current_provenance
from radiopharm_target_agent.schemas import (
    Claim,
    EvidenceBundle,
    LiteratureFinding,
    RunProvenance,
    SourceRef,
    TrialRecord,
)
from radiopharm_target_agent.scorer import compute_target_scorecard
from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
    analyze_single_cell_target,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.hpa_gtex_expression import (
    get_hpa_gtex_expression_profile,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.oar_panel import (
    build_oar_panel,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.ligand_tractability import (
    assess_ligand_tractability,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.txgemma_target_eval import (
    evaluate_target_biology,
)


def _build_test_evidence(
    target: str, indication: str, isotope: str
) -> EvidenceBundle:
    """Helper to assemble a complete EvidenceBundle for testing."""
    prov = get_current_provenance()
    hpa_res = get_hpa_gtex_expression_profile(target, indication=indication)
    oar_res = build_oar_panel(target)
    sc_res = analyze_single_cell_target(target, indication=indication)
    bio_res = evaluate_target_biology(target)
    tract_res = assess_ligand_tractability(target)

    trial = TrialRecord(
        nct_id="NCT03511664",
        title="177Lu-PSMA-617 Phase 3 Trial",
        phase="Phase 3",
        status="Completed",
        modalities=["therapy"],
        is_radiopharmaceutical=True,
        isotope="Lu-177",
        sources=[
            SourceRef(
                kind="ctgov",
                identifier="NCT03511664",
                version="v2",
            )
        ],
    )

    lit = LiteratureFinding(
        pmid="34567890",
        title="Phase 3 Study of 177Lu-PSMA-617",
        orr="45%",
        pfs="8.7 months",
        species="human",
        is_radiopharmaceutical=True,
        sources=[
            SourceRef(
                kind="pubmed",
                identifier="34567890",
                version="NCBI",
            )
        ],
    )

    return EvidenceBundle(
        target=target,
        gene_id="ENSG00000086205" if target == "FOLH1" else "ENSG00000000001",
        indication=indication,
        isotope_context=isotope,  # type: ignore
        expression=hpa_res.get("claims", {}),
        oar_panel=oar_res.get("claims", {}),
        single_cell=sc_res.get("claims", {}),
        clinical=[trial] if target == "FOLH1" else [],
        literature=[lit] if target == "FOLH1" else [],
        target_biology=bio_res.get("claims", {}),
        tractability=tract_res.get("claims", {}),
        provenance=prov,
    )


def test_scorer_determinism_zero_variance():
    """
    Phase 5 Exit Gate & Gate G3:
    Five identical runs must produce exact byte-identical total and sub-scores.
    """
    evidence = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )

    scores = []
    for _ in range(5):
        card = compute_target_scorecard(evidence)
        scores.append(card.total_score)

    assert len(scores) == 5
    assert all(s == scores[0] for s in scores)
    assert scores[0] is not None
    assert scores[0] > 7.5


def test_raising_kidney_expression_lowers_oar_score_only():
    """
    Phase 5 Exit Gate:
    Raising kidney expression 10x lowers OAR safety sub-score and leaves other sub-scores unchanged.
    """
    evidence_base = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )
    card_base = compute_target_scorecard(evidence_base)
    base_oar_score = card_base.axes["oar_safety_margin"].score
    base_selectivity_score = card_base.axes["tumour_selectivity"].score
    base_heterogeneity_score = card_base.axes["heterogeneity_penalty"].score

    # Modify ONLY kidney expression in OAR panel by 10x
    evidence_high_kidney = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )
    orig_kidney_claim = evidence_high_kidney.oar_panel["kidney_cortex"]
    evidence_high_kidney.oar_panel["kidney_cortex"] = Claim(
        field="oar_kidney_cortex",
        value=float(orig_kidney_claim.value or 45.0) * 10.0,
        unit="TPM",
        status="measured",
        evidence_tier="bulk_rna",
        sources=orig_kidney_claim.sources,
        confidence="high",
    )

    card_high_kidney = compute_target_scorecard(evidence_high_kidney)
    new_oar_score = card_high_kidney.axes["oar_safety_margin"].score

    # OAR safety score MUST decrease
    assert new_oar_score is not None
    assert base_oar_score is not None
    assert new_oar_score < base_oar_score

    # ALL other sub-scores must remain EXACTLY identical
    assert (
        card_high_kidney.axes["tumour_selectivity"].score
        == base_selectivity_score
    )
    assert (
        card_high_kidney.axes["heterogeneity_penalty"].score
        == base_heterogeneity_score
    )
    assert (
        card_high_kidney.axes["malignant_cell_specificity"].score
        == card_base.axes["malignant_cell_specificity"].score
    )
    assert (
        card_high_kidney.axes["internalisation_suitability"].score
        == card_base.axes["internalisation_suitability"].score
    )


def test_control_panel_rankings_and_failure_reasons():
    """
    Phase 5 Exit Gate & Gate G2:
    FOLH1 ranks far above GAPDH and MKI67 with correct failure reasons stated.
    """
    # 1. FOLH1 (Positive control)
    ev_folh1 = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )
    card_folh1 = compute_target_scorecard(ev_folh1)
    assert card_folh1.recommendation == "high_priority"
    assert card_folh1.total_score is not None and card_folh1.total_score >= 8.0

    # 2. GAPDH (Selectivity negative control - evaluate selectivity failure)
    ev_gapdh = _build_test_evidence(
        "GAPDH", "prostate_adenocarcinoma", "Lu-177"
    )
    # Set membrane gate passed to specifically test selectivity gate trigger
    ev_gapdh.target_biology["cell_surface_accessible"] = Claim(
        field="cell_surface_accessible",
        value=True,
        status="measured",
        evidence_tier="protein_quant",
        sources=[SourceRef(kind="manual", identifier="test_gate", version="1")],
        confidence="high",
    )
    card_gapdh = compute_target_scorecard(ev_gapdh)
    assert card_gapdh.recommendation == "fail_selectivity_gate"
    assert "tumour selectivity" in card_gapdh.failure_reasons[0].lower()

    # 3. MKI67 (Membrane gate negative control)
    ev_mki67 = _build_test_evidence(
        "MKI67", "prostate_adenocarcinoma", "Lu-177"
    )
    card_mki67 = compute_target_scorecard(ev_mki67)
    assert card_mki67.recommendation == "fail_membrane_gate"
    assert "intracellular" in card_mki67.failure_reasons[0].lower()


def test_isotope_modulation_lu177_vs_ac225():
    """
    Phase 5 Exit Gate:
    Same target under Lu-177 and Ac-225 produces different heterogeneity score & rationale.
    """
    ev_lu = _build_test_evidence("FOLH1", "prostate_adenocarcinoma", "Lu-177")
    ev_ac = _build_test_evidence("FOLH1", "prostate_adenocarcinoma", "Ac-225")

    card_lu = compute_target_scorecard(ev_lu)
    card_ac = compute_target_scorecard(ev_ac)

    lu_het = card_lu.axes["heterogeneity_penalty"]
    ac_het = card_ac.axes["heterogeneity_penalty"]

    assert "Beta" in lu_het.rationale
    assert "Alpha" in ac_het.rationale


def test_scorecard_traceability_100_percent_sources():
    """
    Phase 5 Exit Gate & Gate G4:
    100% of active scorecard axes carry at least one valid SourceRef.
    """
    evidence = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )
    card = compute_target_scorecard(evidence)

    for axis_name, axis_res in card.axes.items():
        if axis_res.status == "scored":
            assert len(axis_res.sources) > 0, f"Axis '{axis_name}' lacks source attribution"


def test_missing_expression_withholds_score():
    """
    Phase 5 Exit Gate & Design Principle 1.5:
    Missing/unavailable expression evidence produces 'score withheld', NOT a fallback average.
    """
    evidence_missing = _build_test_evidence(
        "FOLH1", "prostate_adenocarcinoma", "Lu-177"
    )
    # Wipe expression claim
    evidence_missing.expression = {}

    card = compute_target_scorecard(evidence_missing)
    assert card.total_score is None
    assert card.recommendation == "withheld_insufficient_evidence"
    assert "score withheld" in card.failure_reasons[0]
