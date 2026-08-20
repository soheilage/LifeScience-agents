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
Phase 3 Unit Tests: Single-Cell Transcriptomics & Cell2Sentence (C2S) Deconvolution.

Tests:
1. FAP in pancreatic atlas returns CAF dominance (0% on malignant ductal cells).
2. EPCAM in pancreatic atlas returns malignant ductal epithelial dominance.
3. PTPRC in pancreatic atlas returns immune compartment only.
4. FOLH1 in kidney atlas returns proximal tubule specificity.
5. Gene absent from atlas returns 'not_present_in_dataset' with no synthetic rank.
6. Heterogeneity numerics (% positive malignant cells, dispersion, bimodality).
"""

from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
    analyze_single_cell_target,
)


def test_fap_stroma_negative_control_phase3_exit_gate():
    """
    Phase 3 Exit Gate Requirement:
    FAP in a pancreatic atlas MUST return fibroblast/CAF dominance and NOT malignant ductal cells.
    """
    res = analyze_single_cell_target("FAP", indication="pancreatic_adenocarcinoma")
    assert res["status"] == "success"
    assert res["dominant_compartment"] == "cancer_associated_fibroblast"
    assert res["percent_positive_malignant_cells"] == 0.0
    assert "cancer-associated fibroblasts" in res["summary"]


def test_epcam_malignant_epithelial_specificity():
    """EPCAM in a pancreatic atlas must return malignant epithelial cell dominance."""
    res = analyze_single_cell_target("EPCAM", indication="pancreatic_adenocarcinoma")
    assert res["status"] == "success"
    assert res["dominant_compartment"] == "malignant_ductal_epithelial"
    assert res["percent_positive_malignant_cells"] > 90.0


def test_ptprc_immune_restriction():
    """PTPRC (CD45) must return immune compartment only (0% malignant cells)."""
    res = analyze_single_cell_target("PTPRC", indication="pancreatic_adenocarcinoma")
    assert res["status"] == "success"
    assert res["dominant_compartment"] == "immune"
    assert res["percent_positive_malignant_cells"] == 0.0


def test_folh1_kidney_proximal_tubule_localization():
    """FOLH1 in a normal kidney atlas must return proximal tubule epithelial specificity."""
    res = analyze_single_cell_target("FOLH1", indication="kidney_cortex")
    assert res["status"] == "success"
    assert res["dominant_compartment"] == "proximal_tubule_epithelial"


def test_absent_gene_returns_not_present_without_rank():
    """
    Anti-Hallucination Gate:
    A valid gene absent from a specific atlas (e.g. STEAP1 in pancreatic atlas)
    MUST return 'not_present_in_dataset' and no synthetic rank.
    """
    res = analyze_single_cell_target(
        "STEAP1", indication="pancreatic_adenocarcinoma"
    )
    assert res["status"] == "not_present_in_dataset"
    assert res["dominant_compartment"] is None
    assert res["percent_positive_malignant_cells"] == 0.0
    claim = res["claims"]["single_cell_specificity"]
    assert claim.status == "not_detected"
    assert "not present in single-cell atlas" in claim.caveats[0]


def test_heterogeneity_structured_numerics():
    """Heterogeneity must be output as valid structured numerics."""
    res = analyze_single_cell_target("FOLH1", indication="prostate_adenocarcinoma")
    assert res["status"] == "success"
    assert isinstance(res["percent_positive_malignant_cells"], float)
    assert isinstance(res["dispersion"], float)
    assert isinstance(res["bimodality"], bool)
    assert res["percent_positive_malignant_cells"] > 80.0
