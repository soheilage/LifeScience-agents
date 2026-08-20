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
Unit tests for control target panel frozen fixtures and
Remediation Action 4 single-cell atlas routing regression tests (R-1 to R-7).
"""

import json
from pathlib import Path

from radiopharm_target_agent.provenance import get_current_provenance
from radiopharm_target_agent.schemas import Claim, EvidenceBundle, SourceRef
from radiopharm_target_agent.scorer import compute_target_scorecard
from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
    analyze_single_cell_target,
    route_indication_to_atlas,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "control_panel.json"


def test_control_panel_fixtures_exist():
    assert FIXTURE_PATH.exists()
    with open(FIXTURE_PATH, "r") as f:
        data = json.load(f)

    assert "reference_date" in data
    assert "targets" in data

    targets = data["targets"]
    expected_controls = [
        "FOLH1",
        "SSTR2",
        "FAP",
        "MSLN",
        "ERBB2",
        "GAPDH",
        "MKI67",
        "TP53",
        "FOLH9",
    ]

    for ctrl in expected_controls:
        assert ctrl in targets, f"Missing expected control target: {ctrl}"
        assert "role" in targets[ctrl]
        assert "expected_outcome" in targets[ctrl]


# -----------------------------------------------------------------------------
# Action 4 — Single-Cell Atlas Routing Regression Tests (R-1 through R-7)
# -----------------------------------------------------------------------------


def test_r1_gep_net_routing_does_not_resolve_to_pdac():
    """
    R-1: Indication 'gastroenteropancreatic neuroendocrine tumours'
    Must NOT resolve to any PDAC atlas. Resolves to GEP_NET atlas.
    """
    atlas_info, meta = route_indication_to_atlas(
        "gastroenteropancreatic neuroendocrine tumours"
    )
    assert meta.selected_atlas_id != "PDAC_Peng_Steele_Atlas_v1"
    assert meta.selected_atlas_id == "GEP_NET_Chan_Atlas_v1"
    assert meta.resolution_method == "synonym"

    # Analyze SSTR2 under GEP-NET
    res = analyze_single_cell_target(
        "SSTR2", indication="gastroenteropancreatic neuroendocrine tumours"
    )
    assert res["status"] == "success"
    assert res["dataset_id"] == "GEP_NET_Chan_Atlas_v1"
    assert res["dominant_compartment"] == "malignant_neuroendocrine_epithelial"
    assert res["percent_positive_malignant_cells"] > 90.0


def test_r2_hepatocellular_no_substring_match_fails_closed():
    """
    R-2: Indication 'hepatocellular carcinoma'
    Must NOT resolve via a 'cellular' substring hit. Fails closed to 'no_atlas_for_indication'.
    """
    atlas_info, meta = route_indication_to_atlas("hepatocellular carcinoma")
    assert atlas_info is None
    assert meta.selected_atlas_id is None
    assert meta.resolution_method == "unmapped"

    res = analyze_single_cell_target(
        "GPC3", indication="hepatocellular carcinoma"
    )
    assert res["status"] == "no_atlas_for_indication"
    assert res["dominant_compartment"] is None


def test_r3_cholangiocarcinoma_no_angio_match_fails_closed():
    """
    R-3: Indication 'cholangiocarcinoma'
    Must NOT resolve via an 'angio' substring hit. Fails closed to 'no_atlas_for_indication'.
    """
    atlas_info, meta = route_indication_to_atlas("cholangiocarcinoma")
    assert atlas_info is None
    assert meta.selected_atlas_id is None
    assert meta.resolution_method == "unmapped"

    res = analyze_single_cell_target(
        "FGFR2", indication="cholangiocarcinoma"
    )
    assert res["status"] == "no_atlas_for_indication"


def test_r4_oesophagogastric_junction_fails_closed():
    """
    R-4: Indication 'oesophagogastric junction adenocarcinoma'
    Must NOT silently take a gastric atlas. Fails closed to 'no_atlas_for_indication'.
    """
    atlas_info, meta = route_indication_to_atlas(
        "oesophagogastric junction adenocarcinoma"
    )
    assert atlas_info is None
    assert meta.selected_atlas_id is None
    assert meta.resolution_method == "unmapped"

    res = analyze_single_cell_target(
        "CLDN18", indication="oesophagogastric junction adenocarcinoma"
    )
    assert res["status"] == "no_atlas_for_indication"


def test_r5_merkel_cell_carcinoma_unmapped_axis_withheld():
    """
    R-5: Indication 'Merkel cell carcinoma' (unmapped)
    Returns 'no_atlas_for_indication', run completes, and single-cell axis is withheld.
    """
    res = analyze_single_cell_target(
        "SSTR2", indication="Merkel cell carcinoma"
    )
    assert res["status"] == "no_atlas_for_indication"
    claim = res["claims"]["single_cell_specificity"]
    assert claim.status == "no_atlas_for_indication"
    assert claim.value is None

    # Construct EvidenceBundle with unmapped single-cell axis
    prov = get_current_provenance(sc_routing=res["routing"])
    bundle = EvidenceBundle(
        target="SSTR2",
        gene_id="ENSG00000180616",
        indication="Merkel cell carcinoma",
        isotope_context="Ac-225",
        expression={
            "tumour_vs_normal_ratio": Claim(
                field="tumour_vs_normal_ratio",
                value=25.0,
                status="measured",
                evidence_tier="protein_ihc",
                sources=[SourceRef(kind="hpa", identifier="HPA_SSTR2", version="v23.0")],
            )
        },
        oar_panel={},
        single_cell=res["claims"],
        provenance=prov,
    )
    scorecard = compute_target_scorecard(bundle)
    assert scorecard.axes["malignant_cell_specificity"].status == "withheld"
    assert scorecard.axes["malignant_cell_specificity"].score is None
    assert scorecard.axes["heterogeneity_penalty"].status == "withheld"
    # Total score should not be 0.0 or penalized, but fairly computed over active axes
    assert scorecard.total_score is not None
    assert scorecard.total_score > 7.0


def test_r6_fap_pancreatic_adenocarcinoma_still_resolves_caf():
    """
    R-6: Target FAP in 'pancreatic ductal adenocarcinoma'
    Still resolves to PDAC atlas and returns CAF dominance (confirms rewrite didn't break correct routing).
    """
    atlas_info, meta = route_indication_to_atlas(
        "pancreatic ductal adenocarcinoma"
    )
    assert meta.selected_atlas_id == "PDAC_Peng_Steele_Atlas_v1"
    assert meta.resolution_method in ["exact", "synonym"]

    res = analyze_single_cell_target(
        "FAP", indication="pancreatic ductal adenocarcinoma"
    )
    assert res["status"] == "success"
    assert res["dominant_compartment"] == "cancer_associated_fibroblast"
    assert res["percent_positive_malignant_cells"] == 0.0


def test_r7_scorer_not_detected_vs_no_atlas_withheld():
    """
    R-7: Scorer handling of 'not_detected' vs 'no_atlas_for_indication'.
    - 'not_detected' (queried in atlas, genuinely absent in malignant cells) yields a scored penalty.
    - 'no_atlas_for_indication' withholds the axis without penalizing the total score.
    """
    prov = get_current_provenance()
    source_hpa = SourceRef(kind="hpa", identifier="HPA_TEST", version="v23.0")
    source_c2s = SourceRef(kind="c2s", identifier="C2S_TEST", version="v1.0")

    # Case A: not_detected (queried in registered atlas, gene absent)
    bundle_not_detected = EvidenceBundle(
        target="TEST_A",
        gene_id="ENSG0001",
        indication="prostate_adenocarcinoma",
        isotope_context="Lu-177",
        expression={
            "tumour_vs_normal_ratio": Claim(
                field="tumour_vs_normal_ratio",
                value=20.0,
                status="measured",
                evidence_tier="protein_ihc",
                sources=[source_hpa],
            )
        },
        single_cell={
            "single_cell_specificity": Claim(
                field="single_cell_specificity",
                value="not_detected",
                status="not_detected",
                evidence_tier="sc_rank",
                sources=[source_c2s],
            ),
            "sc_percent_positive_malignant": Claim(
                field="sc_percent_positive_malignant",
                value=0.0,
                status="not_detected",
                evidence_tier="sc_rank",
                sources=[source_c2s],
            ),
        },
        provenance=prov,
    )
    scorecard_not_detected = compute_target_scorecard(bundle_not_detected)
    axis_a = scorecard_not_detected.axes["malignant_cell_specificity"]
    assert axis_a.status == "scored"
    assert axis_a.score == 1.5  # Penalized

    # Case B: no_atlas_for_indication (no atlas registered)
    bundle_unmapped = EvidenceBundle(
        target="TEST_B",
        gene_id="ENSG0002",
        indication="rare_unmapped_neoplasm",
        isotope_context="Lu-177",
        expression={
            "tumour_vs_normal_ratio": Claim(
                field="tumour_vs_normal_ratio",
                value=20.0,
                status="measured",
                evidence_tier="protein_ihc",
                sources=[source_hpa],
            )
        },
        single_cell={
            "single_cell_specificity": Claim(
                field="single_cell_specificity",
                value=None,
                status="no_atlas_for_indication",
                evidence_tier="absent",
                sources=[],
            )
        },
        provenance=prov,
    )
    scorecard_unmapped = compute_target_scorecard(bundle_unmapped)
    axis_b = scorecard_unmapped.axes["malignant_cell_specificity"]
    assert axis_b.status == "withheld"
    assert axis_b.score is None

    # Total score for unmapped must be higher than for genuinely not detected
    assert scorecard_unmapped.total_score is not None
    assert scorecard_not_detected.total_score is not None
    assert scorecard_unmapped.total_score > scorecard_not_detected.total_score
