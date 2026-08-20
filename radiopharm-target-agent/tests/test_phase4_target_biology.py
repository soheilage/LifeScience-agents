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
Phase 4 Unit Tests: Target Biology, Internalization, Shedding, and Tractability.

Tests:
1. MKI67, TP53, and MYC all return cell_surface: False and terminate.
2. FOLH1 returns Type II single-pass; SSTR2 returns 7TM GPCR.
3. MSLN, ERBB2, CEACAM5, and MUC16 return shedding-reported with valid citations; DLL3 returns minimal.
4. Ligand tractability evaluates precedent and binder existence.
5. Ligand toxicity is gated and excluded from scorecard axes.
"""

from radiopharm_target_agent.specialists.target_biology_specialist.tools.ligand_tractability import (
    assess_ligand_tractability,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.predict_toxicity import (
    predict_ligand_toxicity,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.txgemma_target_eval import (
    evaluate_target_biology,
)


def test_intracellular_targets_fail_and_terminate_phase4_exit_gate():
    """
    Phase 4 Exit Gate Requirement:
    MKI67, TP53, and MYC all return cell_surface: FALSE and terminate.
    """
    for target in ["MKI67", "TP53", "MYC"]:
        res = evaluate_target_biology(target)
        assert res["cell_surface"] is False
        assert res["status"] == "fail_membrane_gate"
        assert "Intracellular" in res["topology"] or "failed cell-surface" in res["termination_reason"]


def test_folh1_and_sstr2_topologies_and_internalization():
    """FOLH1 must return type II single-pass; SSTR2 must return 7TM GPCR."""
    folh1_res = evaluate_target_biology("FOLH1")
    assert folh1_res["cell_surface"] is True
    assert "Single-pass type II" in folh1_res["topology"]
    assert folh1_res["internalization_rate"] == "rapid"
    assert len(folh1_res["claims"]["internalization_suitability"].sources) > 0

    sstr2_res = evaluate_target_biology("SSTR2")
    assert sstr2_res["cell_surface"] is True
    assert "7TM GPCR" in sstr2_res["topology"] or "Multi-pass" in sstr2_res["topology"]
    assert sstr2_res["internalization_rate"] == "rapid"


def test_shedding_positive_controls_with_citations_vs_dll3():
    """
    MSLN, ERBB2, CEACAM5, and MUC16 all return shedding-reported with citations;
    DLL3 returns minimal shedding.
    """
    for shed_target in ["MSLN", "ERBB2", "CEACAM5", "MUC16"]:
        res = evaluate_target_biology(shed_target)
        assert res["cell_surface"] is True
        assert res["shedding_reported"] is True
        claim = res["claims"]["shedding_risk"]
        assert len(claim.sources) > 0, f"Missing citation for shed target {shed_target}"

    # DLL3 negative shedding control
    dll3_res = evaluate_target_biology("DLL3")
    assert dll3_res["cell_surface"] is True
    assert dll3_res["shedding_reported"] is False


def test_ligand_tractability_assessment():
    """Evaluates binder availability and clinical radioligand precedent."""
    folh1_tract = assess_ligand_tractability("FOLH1")
    assert folh1_tract["status"] == "success"
    assert folh1_tract["tractability_score"] >= 9.0
    assert any("Pluvicto" in r for r in folh1_tract["established_radioligands"])

    sstr2_tract = assess_ligand_tractability("SSTR2")
    assert sstr2_tract["status"] == "success"
    assert any("Lutathera" in r for r in sstr2_tract["established_radioligands"])


def test_ligand_toxicity_gating_and_scorecard_exclusion():
    """Predict toxicity tool is gated and labeled as excluded from scorecard."""
    # When no SMILES is passed, bypassed cleanly
    res_bypassed = predict_ligand_toxicity(None)
    assert res_bypassed["status"] == "bypassed"
    assert res_bypassed["excluded_from_target_scorecard"] is True

    # Empty SMILES
    res_empty = predict_ligand_toxicity("")
    assert res_empty["status"] == "bypassed"
