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
Unit tests for guards.py — validating anti-hallucination gates G1 and G2.
"""

from radiopharm_target_agent.guards import (
    check_membrane_gate,
    enforce_citation_or_abstain,
    resolve_gene_symbol,
    validate_nct_id,
    validate_pmid,
)


def test_nct_validation():
    assert validate_nct_id("NCT03511664") is True
    assert validate_nct_id("NCT12345678") is True
    assert validate_nct_id("NCT12345") is False  # too short
    assert validate_nct_id("12345678") is False  # missing NCT prefix
    assert validate_nct_id("NCT03511664A") is False  # trailing alpha
    assert validate_nct_id("") is False


def test_pmid_validation():
    assert validate_pmid("34567890") is True
    assert validate_pmid("12345") is True
    assert validate_pmid("PMC12345") is False  # PMCID, not PMID
    assert validate_pmid("invalid") is False
    assert validate_pmid("") is False


def test_gene_symbol_resolution_and_disambiguation():
    # PSMA alias resolution
    res_psma = resolve_gene_symbol("PSMA")
    assert res_psma["status"] == "resolved"
    assert res_psma["canonical_symbol"] == "FOLH1"
    assert "PSMA1-PSMA7" in res_psma["disambiguation_note"]

    # HER2 alias resolution
    res_her2 = resolve_gene_symbol("HER2")
    assert res_her2["status"] == "resolved"
    assert res_her2["canonical_symbol"] == "ERBB2"

    # Direct resolution
    res_sstr2 = resolve_gene_symbol("SSTR2")
    assert res_sstr2["status"] == "resolved"
    assert res_sstr2["canonical_symbol"] == "SSTR2"


def test_gene_abstention_gate_g2():
    # Unrecognised / invalid control symbol FOLH9
    res_folh9 = resolve_gene_symbol("FOLH9")
    assert res_folh9["status"] == "abstain"
    assert res_folh9["canonical_symbol"] is None
    assert "Abstaining" in res_folh9["reason"]


def test_membrane_accessibility_gate_g2():
    # Positive controls: Cell surface / transmembrane
    pass_folh1, msg1 = check_membrane_gate(
        "Single-pass type II", ["Plasma membrane"], "FOLH1"
    )
    assert pass_folh1 is True

    pass_sstr2, msg2 = check_membrane_gate(
        "Multi-pass membrane protein", ["Cell membrane"], "SSTR2"
    )
    assert pass_sstr2 is True

    # Negative controls: Intracellular / nuclear
    pass_mki67, msg3 = check_membrane_gate(
        "Nuclear matrix", ["Nucleus"], "MKI67"
    )
    assert pass_mki67 is False
    assert "failed cell-surface membrane gate" in msg3

    pass_tp53, msg4 = check_membrane_gate(
        "Cytosolic / Nuclear", ["Nucleus"], "TP53"
    )
    assert pass_tp53 is False
    assert "failed cell-surface membrane gate" in msg4


def test_citation_enforcement():
    claims = [
        {
            "field": "valid_claim",
            "value": 10.0,
            "status": "measured",
            "sources": [{"kind": "gtex", "identifier": "1", "version": "v8"}],
        },
        {
            "field": "invalid_claim",
            "value": 50.0,
            "status": "measured",
            "sources": [],  # lacks source
        },
    ]
    filtered = enforce_citation_or_abstain(claims)
    assert len(filtered) == 2
    assert filtered[0]["status"] == "measured"
    assert filtered[1]["status"] == "unavailable"
    assert filtered[1]["value"] is None


def test_fact_consistency_gate_contradiction_halts_run():
    """
    Gap A Regression Test: Injecting two contradictory isotope claims for the same trial ID
    causes check_fact_consistency_gate to fail and compute_target_scorecard to halt with 'halt_on_contradiction'.
    """
    from datetime import datetime, timezone
    from radiopharm_target_agent.guards import check_fact_consistency_gate
    from radiopharm_target_agent.schemas import EvidenceBundle, RunProvenance, SourceRef, TrialRecord
    from radiopharm_target_agent.scorer import compute_target_scorecard

    # Contradictory trial records for same NCT05477576 (Ac-225 vs Lu-177)
    t1 = TrialRecord(
        nct_id="NCT05477576",
        title="ACTION-1 Ac-225 Arm",
        phase="Phase 1b",
        status="Recruiting",
        modalities=["therapy"],
        is_radiopharmaceutical=True,
        isotope="Ac-225",
        sources=[SourceRef(kind="ctgov", identifier="NCT05477576", version="API_v2")],
    )
    t2 = TrialRecord(
        nct_id="NCT05477576",
        title="ACTION-1 Lu-177 Arm (Contradictory Injection)",
        phase="Phase 1b",
        status="Recruiting",
        modalities=["therapy"],
        is_radiopharmaceutical=True,
        isotope="Lu-177",
        sources=[SourceRef(kind="ctgov", identifier="NCT05477576", version="API_v2")],
    )

    bundle = EvidenceBundle(
        target="SSTR2",
        gene_id="ENSG00000180616",
        indication="gastroenteropancreatic neuroendocrine tumours",
        isotope_context="Ac-225",
        clinical=[t1, t2],
        provenance=RunProvenance(timestamp=datetime.now(timezone.utc)),
    )

    is_consistent, contradictions = check_fact_consistency_gate(bundle)
    assert is_consistent is False
    assert len(contradictions) == 1
    assert "Contradictory isotope attribution" in contradictions[0]

    # Verify compute_target_scorecard halts
    scorecard = compute_target_scorecard(bundle)
    assert scorecard.recommendation == "halt_on_contradiction"
    assert scorecard.total_score == 0.0
    assert len(scorecard.failure_reasons) == 1

