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
Trace Review Remediation Tests (B1 through B8).

Validates all 8 confirmed concerns from the SSTR2 Ac-225 GEP-NET trace review:
- B1 (C1): ACTION-1 / RYZ101 intervention isotope extraction and contradiction gate.
- B2 (C2): Single-cell atlas SHA-256 checksum and formal Gini / dispersion definitions.
- B3 (C3): OAR delivery accessibility (BBB protection) & non-target PK liabilities (renal reabsorption).
- B4 (C4): Tractability score derivation formula.
- B5 (C5): 8-axis scorecard generation wired to Writer tool.
- B6 (C6): Topology-aware GPCR extracellular architecture.
- B7 (C7): Epistemic absence-of-evidence status for shedding ('not_reported', low confidence).
- B8 (C8): Verified GEP-NET atlas DOI and accession.
"""

from pathlib import Path
import pytest
from radiopharm_target_agent.provenance import format_provenance_banner, get_current_provenance
from radiopharm_target_agent.schemas import EvidenceBundle, SingleCellRoutingMetadata, SourceRef, TrialRecord
from radiopharm_target_agent.scorer import compute_target_scorecard, generate_target_scorecard_table
from radiopharm_target_agent.specialists.clinical_specialist.tools.search_clinical_trials import (
    classify_modalities_and_isotopes,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
    analyze_single_cell_target,
    get_atlas_registry_checksum,
    load_atlas_registry,
    route_indication_to_atlas,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.oar_panel import (
    build_oar_panel,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.uniprot_annotations import (
    get_uniprot_target_annotations,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.txgemma_target_eval import (
    evaluate_target_biology,
)


def test_b1_ryz101_isotope_attribution():
    """
    B1 (C1): ACTION-1 trial with intervention 'RYZ101' ([225Ac]-DOTATATE)
    must extract Ac-225 and 'therapy' modality, without being overridden by
    prior therapy text ('progressed following 177Lu-SSA therapy').
    """
    study_text = "Phase 1b/3 Study of 225Ac-DOTATATE (RYZ101) in Patients With Inoperable GEP-NETs Progressed Following 177Lu-SSA Therapy"
    interventions = [
        {"name": "RYZ101", "description": "225Ac-DOTATATE administered intravenously"}
    ]
    modalities, detected_iso, is_radio = classify_modalities_and_isotopes(
        study_text, interventions=interventions
    )
    assert is_radio is True
    assert "therapy" in modalities
    assert detected_iso == "Ac-225"


def test_b2_atlas_checksum_and_metrics():
    """
    B2 (C2): Checksum is emitted in routing metadata and Gini + Dispersion metrics
    are typed and distinct.
    """
    checksum = get_atlas_registry_checksum()
    assert len(checksum) == 64  # Valid SHA-256 hex string

    res = analyze_single_cell_target("SSTR2", indication="gastroenteropancreatic neuroendocrine tumours")
    assert res["status"] == "success"
    assert res["percent_positive_malignant_cells"] == 91.2
    assert res["dispersion"] == 0.21
    assert res["gini_coefficient"] == 0.26

    # Verify routing metadata carries SHA-256
    routing = res["routing"]
    assert routing["atlas_sha256"] == checksum
    assert routing["geo_accession"] == "GSE211485"
    assert routing["publication_doi"] == "10.1186/s12943-025-02231-y"


def test_b3_oar_delivery_accessibility_and_pk_liabilities():
    """
    B3 (C3): OAR panel distinguishes on-target BBB penetration (brain is shielded for peptide)
    from non-target-mediated renal reabsorption (kidney proximal tubule megalin uptake).
    """
    oar_res = build_oar_panel("SSTR2")
    claims = oar_res["claims"]
    assert claims["brain"].delivery_accessibility == "bbb_protected"
    assert claims["kidney_cortex"].delivery_accessibility == "actively_reabsorbing"

    # In EvidenceBundle for peptide vector
    bundle = EvidenceBundle(
        target="SSTR2",
        gene_id="ENSG00000180616",
        indication="gastroenteropancreatic neuroendocrine tumours",
        isotope_context="Ac-225",
        vector_class="peptide",
        oar_panel=claims,
        provenance=get_current_provenance(),
    )
    scorecard = compute_target_scorecard(bundle)
    oar_axis = scorecard.axes["oar_safety_margin"]

    # Verify brain neurotoxicity warning is avoided / BBB noted
    assert any("blood-brain barrier" in c.lower() for c in oar_axis.caveats)
    # Verify renal tubular reabsorption PK liability is surfaced
    assert any("megalin/cubilin" in c.lower() for c in oar_axis.caveats)


def test_b4_tractability_score_derivation():
    """
    B4 (C4): Tractability score is derived deterministically from formula components.
    """
    trial_approved = TrialRecord(
        nct_id="NCT01578239",
        title="Approved 177Lu-DOTATATE (Lutathera)",
        phase="Phase 3",
        status="Completed",
        modalities=["therapy"],
        is_radiopharmaceutical=True,
        isotope="Lu-177",
        sources=[SourceRef(kind="ctgov", identifier="NCT01578239", version="API_v2")],
    )
    bundle = EvidenceBundle(
        target="SSTR2",
        gene_id="ENSG00000180616",
        indication="gastroenteropancreatic neuroendocrine tumours",
        isotope_context="Ac-225",
        clinical=[trial_approved],
        provenance=get_current_provenance(),
    )
    scorecard = compute_target_scorecard(bundle)
    tract_axis = scorecard.axes["tractability"]
    assert tract_axis.score is not None
    assert tract_axis.score >= 8.5
    assert "precedent" in tract_axis.rationale.lower()


def test_b5_generate_target_scorecard_table():
    """
    B5 (C5): generate_target_scorecard_table executes and formats all 8 axes into Markdown.
    """
    table_md = generate_target_scorecard_table(
        target="SSTR2",
        indication="gastroenteropancreatic neuroendocrine tumours",
        isotope="Ac-225",
        vector_class="peptide",
    )
    assert "### Target Prioritisation Scorecard: `SSTR2`" in table_md
    assert "Tumour Selectivity" in table_md
    assert "Oar Safety Margin" in table_md
    assert "Malignant Cell Specificity" in table_md
    assert "Heterogeneity Penalty" in table_md
    assert "Internalisation Suitability" in table_md
    assert "Shedding Penalty" in table_md
    assert "Clinical Pipeline Maturity" in table_md
    assert "Tractability" in table_md


def test_b6_gpcr_extracellular_architecture():
    """
    B6 (C6): UniProt annotations for SSTR2 report GPCR 7TM topology with extracellular loops
    and do not mischaracterize it as a single continuous ECD.
    """
    annot = get_uniprot_target_annotations("SSTR2")
    assert "7TM" in annot["topology"] or "Multi-pass" in annot["topology"]
    assert annot["membrane_gate_passed"] is True


def test_b7_shedding_epistemic_absence_of_evidence():
    """
    B7 (C7): SSTR2 shedding status is 'not_reported' with 'low' confidence,
    not fabricated as experimental proof of absence.
    """
    bio_res = evaluate_target_biology("SSTR2")
    shedding_claim = bio_res["claims"]["shedding_risk"]
    assert shedding_claim.status == "not_reported"
    assert shedding_claim.confidence == "low"
    assert len(shedding_claim.sources) == 0


def test_b8_gep_net_atlas_doi():
    """
    B8 (C8): Verified GEP-NET publication DOI in registry is Zhou et al. Mol Cancer 2025.
    """
    registry = load_atlas_registry()
    atlas_map = {a["id"]: a for a in registry["atlases"]}
    gep_atlas = atlas_map["GEP_NET_Chan_Atlas_v1"]
    assert gep_atlas["publication_doi"] == "10.1186/s12943-025-02231-y"
    assert gep_atlas["geo_accession"] == "GSE211485"


def test_r1_population_validation_mismatch_refuses_to_load():
    """
    R1 Regression Test: Registering an atlas whose declared population does not match its registered indication
    causes validate_atlas_registry_populations to raise ValueError and refuse to load.
    """
    import pytest
    from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
        validate_atlas_registry_populations,
    )

    bad_registry = {
        "atlases": [
            {
                "id": "MOCK_MISMATCHED_ATLAS",
                "population": "colorectal_neuroendocrine_tumour",
                "indications": ["gastroenteropancreatic_neuroendocrine_tumour"],
            }
        ],
        "indication_ontology": {
            "gastroenteropancreatic_neuroendocrine_tumour": {
                "synonyms": ["gep_net", "gepnet"]
            }
        },
    }

    with pytest.raises(ValueError) as excinfo:
        validate_atlas_registry_populations(bad_registry)

    assert "Population mismatch in atlas 'MOCK_MISMATCHED_ATLAS'" in str(excinfo.value)
    assert "does not match registered indication" in str(excinfo.value)
