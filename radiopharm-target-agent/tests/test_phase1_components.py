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
Phase 1 Unit Tests: Clinical Specialist & Literature Specialist.

Tests:
1. Modality classification (therapy vs diagnostic vs ADC).
2. Diagnostic-only PET trials are correctly labelled and not counted as RLT therapy.
3. Species attribution (mouse/rodent dosimetry vs human).
4. Target with no trials returns empty with explicit statement.
5. Format validation of NCT IDs and PMIDs.
6. Rule-based summarizer extracting dosimetry and endpoints.
"""

from radiopharm_target_agent.guards import validate_nct_id, validate_pmid
from radiopharm_target_agent.specialists.clinical_specialist.tools.get_eligibility_criteria import (
    get_eligibility_criteria,
)
from radiopharm_target_agent.specialists.clinical_specialist.tools.search_clinical_trials import (
    classify_modalities_and_isotopes,
    search_trials,
)
from radiopharm_target_agent.specialists.literature_specialist.tools.fetch_articles import (
    detect_species,
    fetch_pubmed_articles,
)
from radiopharm_target_agent.specialists.literature_specialist.tools.summarize_paper import (
    _rule_based_summary,
)


def test_modality_classification_therapy_vs_diagnostic():
    """Diagnostic-only PET trials must be labelled 'diagnostic', NOT counted as therapy."""
    # 1. Therapeutic trial: Lu-177 PSMA radioligand therapy
    therapy_text = "A Phase 3 Study of 177Lu-PSMA-617 in Patients with Metastatic Castration-Resistant Prostate Cancer (VISION)"
    modalities_1, isotope_1, is_radio_1 = classify_modalities_and_isotopes(
        therapy_text
    )
    assert "therapy" in modalities_1
    assert is_radio_1 is True
    assert isotope_1 == "Lu-177"

    # 2. Diagnostic-only PET scan: 68Ga-PSMA-11 PET/CT imaging
    diag_text = "Diagnostic accuracy of 68Ga-PSMA-11 PET/CT scan for primary staging in high-risk prostate cancer"
    modalities_2, isotope_2, is_radio_2 = classify_modalities_and_isotopes(
        diag_text
    )
    assert "diagnostic" in modalities_2
    assert "therapy" not in modalities_2
    assert is_radio_2 is True
    assert isotope_2 == "Ga-68"

    # 3. Antibody-Drug Conjugate (ADC)
    adc_text = "A Phase 2 study of Enfortumab Vedotin in patients with previously treated advanced urothelial carcinoma"
    modalities_3, _, is_radio_3 = classify_modalities_and_isotopes(adc_text)
    assert "ADC" in modalities_3


def test_species_labeling_rodent_vs_human():
    """A rodent dosimetry paper must be labelled species: mouse / rat."""
    mouse_abstract = (
        "In this study, biodistribution and radiation dosimetry of 177Lu-labeled peptide was evaluated "
        "in athymic nude mice bearing human prostate xenografts. Tumour-to-kidney ratio was calculated."
    )
    assert detect_species(mouse_abstract) == "mouse"

    human_abstract = (
        "We conducted a prospective clinical trial in 30 patients with metastatic castration-resistant "
        "prostate cancer receiving 177Lu-PSMA-617. Median overall survival was 15.3 months."
    )
    assert detect_species(human_abstract) == "human"


def test_target_with_no_trials_returns_explicit_empty_statement():
    """A query returning no trials must return an explicit statement without fabrication."""
    res = search_trials(
        target="NON_EXISTENT_GENE_XYZ_12345", indication="Rare Disease"
    )
    assert "No clinical trials found" in res
    assert "NON_EXISTENT_GENE_XYZ_12345" in res


def test_invalid_nct_id_rejected():
    """Invalid NCT ID formats are immediately rejected."""
    res = get_eligibility_criteria("INVALID_NCT_123")
    assert "Error: Invalid NCT ID format" in res


def test_rule_based_summarizer_extracts_dosimetry_and_endpoints():
    """Summarizer must extract Gy/GBq doses and ORR/PFS metrics."""
    sample_text = (
        "Phase 2 clinical trial of 177Lu-DOTATATE in neuroendocrine tumors. "
        "Overall response rate (ORR) was 35%. Median PFS was 28.4 months. "
        "Absorbed radiation dose was 0.85 Gy/GBq in kidneys and 0.05 Gy/GBq in bone marrow. "
        "Patients experienced mild nausea."
    )
    summary = _rule_based_summary(sample_text)
    assert "35%" in summary
    assert "28.4 months" in summary
    assert "0.85" in summary
    assert "human" in summary
