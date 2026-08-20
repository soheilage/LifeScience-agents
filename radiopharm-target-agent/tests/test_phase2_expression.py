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
Phase 2 Unit Tests: Expression Specialist, OAR panel, and UniProt annotations.

Tests:
1. lacrimal_gland and bone_marrow return 'not_measured', never 'not_detected' or '0'.
2. GAPDH fails tumour selectivity (T/N ~ 1.09).
3. MKI67 & TP53 fail the cell-surface membrane gate.
4. FOLH9 triggers strict abstention.
5. 'PSMA' resolves to FOLH1 with explicit exclusion note for PSMA1-7.
6. Three identical queries return byte-identical payloads (determinism).
"""

import json
from radiopharm_target_agent.specialists.expression_specialist.tools.hpa_gtex_expression import (
    get_hpa_gtex_expression_profile,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.oar_panel import (
    build_oar_panel,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.uniprot_annotations import (
    get_uniprot_target_annotations,
)


def test_oar_missing_data_rule_phase2_exit_gate():
    """
    Phase 2 Exit Gate Requirement:
    lacrimal_gland and bone_marrow MUST return 'not_measured', never 'not_detected' or '0'.
    """
    oar_res = build_oar_panel("FOLH1")
    claims = oar_res["claims"]

    # 1. Check lacrimal gland
    assert "lacrimal_gland" in claims
    claim_lacrimal = claims["lacrimal_gland"]
    assert claim_lacrimal.status == "not_measured"
    assert claim_lacrimal.value is None
    assert claim_lacrimal.status != "not_detected"
    assert claim_lacrimal.value != 0

    # 2. Check bone marrow
    assert "bone_marrow" in claims
    claim_marrow = claims["bone_marrow"]
    assert claim_marrow.status == "not_measured"
    assert claim_marrow.value is None
    assert claim_marrow.status != "not_detected"
    assert claim_marrow.value != 0

    # 3. Check that kidney_cortex IS measured for FOLH1
    assert "kidney_cortex" in claims
    claim_kidney = claims["kidney_cortex"]
    assert claim_kidney.status == "measured"
    assert claim_kidney.value > 0


def test_gapdh_fails_selectivity_gate():
    """GAPDH is ubiquitous and must have a T/N ratio near 1.0 (fails selectivity)."""
    gapdh_res = get_hpa_gtex_expression_profile(
        "GAPDH", indication="prostate_adenocarcinoma"
    )
    assert gapdh_res["status"] == "success"
    tn_ratio = gapdh_res["tumour_vs_normal_ratio"]
    assert (
        tn_ratio < 2.0
    )  # Near 1.09, fails threshold for radioligand selectivity


def test_mki67_and_tp53_fail_membrane_gate():
    """MKI67 and TP53 are intracellular and must fail the membrane gate."""
    mki67_res = get_uniprot_target_annotations("MKI67")
    assert mki67_res["membrane_gate_passed"] is False
    assert "failed cell-surface membrane gate" in mki67_res["membrane_gate_message"]

    tp53_res = get_uniprot_target_annotations("TP53")
    assert tp53_res["membrane_gate_passed"] is False
    assert "failed cell-surface membrane gate" in tp53_res["membrane_gate_message"]


def test_folh9_triggers_abstention():
    """Unrecognised gene symbol FOLH9 must trigger abstention without confabulation."""
    res_expr = get_hpa_gtex_expression_profile("FOLH9")
    assert res_expr["status"] == "abstain"
    assert "Abstaining" in res_expr["reason"]

    res_oar = build_oar_panel("FOLH9")
    assert res_oar["status"] == "abstain"

    res_uniprot = get_uniprot_target_annotations("FOLH9")
    assert res_uniprot["status"] == "abstain"


def test_psma_alias_resolution_and_disambiguation_note():
    """'PSMA' must resolve to FOLH1 with explicit exclusion of PSMA1-7."""
    res = get_hpa_gtex_expression_profile("PSMA")
    assert res["status"] == "success"
    assert res["canonical_symbol"] == "FOLH1"
    assert "PSMA1-PSMA7" in res["disambiguation_note"]


def test_determinism_byte_identical_payloads():
    """Three identical queries must return byte-identical JSON payloads."""
    payloads = []
    for _ in range(3):
        res = get_hpa_gtex_expression_profile(
            "FOLH1", indication="prostate_adenocarcinoma"
        )
        # Convert claims to serializable dicts
        serializable = {
            "status": res["status"],
            "target": res["target"],
            "canonical_symbol": res["canonical_symbol"],
            "ensembl_id": res["ensembl_id"],
            "tumour_vs_normal_ratio": res["tumour_vs_normal_ratio"],
            "claims": {k: v.model_dump(mode="json") for k, v in res["claims"].items()},
        }
        json_str = json.dumps(serializable, sort_keys=True)
        payloads.append(json_str)

    assert payloads[0] == payloads[1]
    assert payloads[1] == payloads[2]
