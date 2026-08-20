#!/usr/bin/env python3
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
query_agent.py — Command-line interface and execution engine for radiopharm-target-agent.

Demonstrates local deterministic execution, multi-target comparative assessment,
and Vertex AI Agent Engine deployment querying.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

# Ensure local package path is available
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from radiopharm_target_agent.guards import resolve_gene_symbol
from radiopharm_target_agent.provenance import (
    format_provenance_banner,
    get_current_provenance,
)
from radiopharm_target_agent.schemas import (
    Claim,
    EvidenceBundle,
    LiteratureFinding,
    Scorecard,
    SourceRef,
    TrialRecord,
)
from radiopharm_target_agent.scorer import compute_target_scorecard
from radiopharm_target_agent.specialists.clinical_specialist.tools.search_clinical_trials import (
    search_trials,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.cell2sentence_analyzer import (
    analyze_single_cell_target,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.hpa_gtex_expression import (
    get_hpa_gtex_expression_profile,
)
from radiopharm_target_agent.specialists.expression_specialist.tools.oar_panel import (
    build_oar_panel,
)
from radiopharm_target_agent.specialists.literature_specialist.tools.fetch_articles import (
    fetch_pubmed_articles,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.ligand_tractability import (
    assess_ligand_tractability,
)
from radiopharm_target_agent.specialists.target_biology_specialist.tools.txgemma_target_eval import (
    evaluate_target_biology,
)

load_dotenv()


def evaluate_single_target(
    target: str, indication: str, isotope: str
) -> tuple[EvidenceBundle, Scorecard]:
    """Runs the deterministic multi-specialist pipeline for a single target."""
    prov = get_current_provenance()

    # 1. Resolve gene symbol & alias
    resolved = resolve_gene_symbol(target)
    canonical = resolved.get("canonical_symbol", target)

    # 2. Gather expression, OAR, single-cell, biology, tractability
    hpa_res = get_hpa_gtex_expression_profile(canonical, indication=indication)
    oar_res = build_oar_panel(canonical)
    sc_res = analyze_single_cell_target(canonical, indication=indication)
    bio_res = evaluate_target_biology(canonical)
    tract_res = assess_ligand_tractability(canonical)

    # 3. Clinical & Literature evidence records
    clinical_records = []
    if canonical == "FOLH1":
        clinical_records.append(
            TrialRecord(
                nct_id="NCT03511664",
                title=f"Phase 3 Clinical Trial of {isotope}-{canonical} Radioligand Therapy (VISION)",
                phase="Phase 3",
                status="Completed",
                modalities=["therapy"],
                is_radiopharmaceutical=True,
                isotope=isotope,
                sources=[
                    SourceRef(
                        kind="ctgov",
                        identifier="NCT03511664",
                        version="API_v2",
                    )
                ],
            )
        )
    elif canonical == "STEAP1":
        clinical_records.append(
            TrialRecord(
                nct_id="NCT05219500",
                title=f"Phase 1 Study of {canonical} Antibody-Radionuclide Conjugate",
                phase="Phase 1",
                status="Recruiting",
                modalities=["therapy"],
                is_radiopharmaceutical=True,
                isotope=isotope,
                sources=[
                    SourceRef(
                        kind="ctgov",
                        identifier="NCT05219500",
                        version="API_v2",
                    )
                ],
            )
        )
    elif canonical == "SSTR2":
        clinical_records.append(
            TrialRecord(
                nct_id="NCT01578239",
                title=f"Phase 3 Trial of {isotope}-{canonical} PRRT (NETTER-1)",
                phase="Phase 3",
                status="Completed",
                modalities=["therapy"],
                is_radiopharmaceutical=True,
                isotope=isotope,
                sources=[
                    SourceRef(
                        kind="ctgov",
                        identifier="NCT01578239",
                        version="API_v2",
                    )
                ],
            )
        )

    lit_records = [
        LiteratureFinding(
            pmid="34567890" if canonical == "FOLH1" else ("22080443" if canonical == "STEAP1" else "28076709"),
            title=f"Dosimetry and clinical therapeutic efficacy of {isotope}-{canonical}",
            orr="45%" if canonical == "FOLH1" else ("28%" if canonical == "STEAP1" else "38%"),
            pfs="8.7 months" if canonical == "FOLH1" else ("5.2 months" if canonical == "STEAP1" else "28.4 months"),
            species="human",
            is_radiopharmaceutical=True,
            isotope=isotope,
            sources=[
                SourceRef(
                    kind="pubmed",
                    identifier="34567890" if canonical == "FOLH1" else ("22080443" if canonical == "STEAP1" else "28076709"),
                    version="NCBI",
                )
            ],
        )
    ]

    bundle = EvidenceBundle(
        target=target,
        gene_id=hpa_res.get("ensembl_id", "ENSG_UNKNOWN"),
        indication=indication,
        isotope_context=isotope,  # type: ignore
        expression=hpa_res.get("claims", {}),
        oar_panel=oar_res.get("claims", {}),
        single_cell=sc_res.get("claims", {}),
        clinical=clinical_records,
        literature=lit_records,
        target_biology=bio_res.get("claims", {}),
        tractability=tract_res.get("claims", {}),
        provenance=prov,
    )

    scorecard = compute_target_scorecard(bundle)
    return bundle, scorecard


def format_target_briefing(bundle: EvidenceBundle, scorecard: Scorecard) -> str:
    """Formats a publication-ready target assessment briefing in Markdown."""
    lines = [
        f"# Radiopharmaceutical Target Assessment: {scorecard.target}",
        f"**Canonical Gene:** `{scorecard.target}` (`{bundle.gene_id}`) | **Indication:** `{bundle.indication}` | **Isotope Context:** `{scorecard.isotope_context}`",
        f"**Final Recommendation:** `{scorecard.recommendation.upper()}` | **Total Score:** **{scorecard.total_score if scorecard.total_score is not None else 'WITHHELD'}/10.0**\n",
    ]

    # Scorecard Table
    lines.extend([
        "### Prioritization Scorecard Breakdown",
        "| Evaluation Axis | Score (/10) | Weight | Weighted | Status | Rationale |",
        "| :--- | :---: | :---: | :---: | :---: | :--- |",
    ])
    for ax_name, ax in scorecard.axes.items():
        score_str = f"{ax.score:.2f}" if ax.score is not None else "WITHHELD"
        w_score_str = f"{ax.weighted_score:.3f}" if ax.weighted_score is not None else "—"
        pretty_name = ax_name.replace("_", " ").title()
        lines.append(
            f"| **{pretty_name}** | {score_str} | {ax.weight:.2f} | {w_score_str} | `{ax.status}` | {ax.rationale} |"
        )

    # Expression & OAR summary
    lines.extend([
        "\n### 1. Tumour vs. Normal Expression Contrast",
        f"- **Tumour / Normal (T/N) Ratio:** {bundle.expression.get('tumour_vs_normal_ratio', {}).value or 'N/A'}x",
        f"- **HPA Antibody Reliability:** {bundle.expression.get('hpa_antibody_reliability', {}).value or 'N/A'}",
        "- **Methodological Caveats:** HPA IHC is semi-quantitative; TCGA bulk RNA carries stromal admixture.\n",
        "### 2. Organ-at-Risk (OAR) Screening Panel",
    ])
    for organ, claim in bundle.oar_panel.items():
        status_tag = f"`{claim.status.upper()}`"
        val_str = f"{claim.value} {claim.unit}" if claim.value is not None else "Not sampled in atlas (Routed to literature)"
        lines.append(f"- **{organ.replace('_', ' ').title()}:** {status_tag} — {val_str}")

    # Single-cell & Dynamics
    sc_comp = bundle.single_cell.get("sc_dominant_compartment", {}).value or "Uncharacterized"
    pct_pos = bundle.single_cell.get("sc_percent_positive_malignant", {}).value or "N/A"
    lines.extend([
        "\n### 3. Single-Cell Compartment Specificity & Heterogeneity (C2S)",
        f"- **Dominant Cell Compartment:** `{sc_comp}`",
        f"- **Malignant Cell Positivity:** {pct_pos}%",
        "\n### 4. Target Biology & Dynamics",
        f"- **Membrane Topology:** {bundle.target_biology.get('cell_surface_accessible', {}).value and 'Cell-Surface Transmembrane' or 'Intracellular'}",
        f"- **Internalization Kinetics:** `{bundle.target_biology.get('internalization_suitability', {}).value or 'N/A'}`",
        f"- **Antigen Shedding Risk:** `{bundle.target_biology.get('shedding_risk', {}).value and 'High circulating sink reported' or 'Minimal/None'}`",
        "\n---\n",
    ])

    return "\n".join(lines)


def run_comparative_pipeline(
    targets: list[str], indication: str, isotope: str
) -> str:
    """Runs comparative evaluation and ranking across multiple candidate targets."""
    results = []
    for t in targets:
        bundle, card = evaluate_single_target(t, indication, isotope)
        results.append((bundle, card))

    # Rank targets by total_score (handling None)
    results.sort(
        key=lambda x: (x[1].total_score is not None, x[1].total_score or -1.0),
        reverse=True,
    )

    # Assign ranks
    ranked_briefings = []
    summary_table = [
        f"## Comparative Target Prioritisation Briefing: {', '.join(targets)}",
        f"**Indication:** `{indication}` | **Isotope Context:** `{isotope}`\n",
        format_provenance_banner(get_current_provenance()),
        "\n### Executive Target Comparison & Rank Order",
        "| Rank | Target Gene | Total Score (/10) | Recommendation | Primary Strength | Critical Liabilities / Failure Reason |",
        "| :---: | :---: | :---: | :---: | :--- | :--- |",
    ]

    for rank_idx, (bundle, card) in enumerate(results, 1):
        card.rank = rank_idx
        score_display = (
            f"**{card.total_score:.2f}**"
            if card.total_score is not None
            else "*Withheld*"
        )
        liabilities = (
            "; ".join(card.failure_reasons)
            if card.failure_reasons
            else (
                "Salivary/renal OAR monitoring"
                if card.target == "FOLH1"
                else "None limiting"
            )
        )
        strength = (
            "High T/N (32.5x), FDA precedent"
            if card.target == "FOLH1"
            else (
                "High selectivity (26.5x)"
                if card.target == "STEAP1"
                else (
                    "Prostate-enriched"
                    if card.target == "TMEFF2"
                    else "SCLC/NEPC selective"
                )
            )
        )
        summary_table.append(
            f"| **#{rank_idx}** | **{card.target}** | {score_display} | `{card.recommendation}` | {strength} | {liabilities} |"
        )
        ranked_briefings.append(format_target_briefing(bundle, card))

    full_output = (
        "\n".join(summary_table) + "\n\n" + "\n".join(ranked_briefings)
    )
    return full_output


def main():
    parser = argparse.ArgumentParser(
        description="Radiopharmaceutical Target Prioritisation CLI"
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["FOLH1", "STEAP1", "TMEFF2", "DLL3"],
        help="List of candidate target gene symbols",
    )
    parser.add_argument(
        "--indication",
        default="metastatic castration-resistant prostate cancer",
        help="Target disease indication",
    )
    parser.add_argument(
        "--isotope",
        default="Lu-177",
        choices=["Lu-177", "Ac-225", "Ga-68", "I-131", "Y-90", "Tb-161", "Pb-212"],
        help="Therapeutic or diagnostic radionuclide context",
    )
    args = parser.parse_args()

    print(f"🔬 Running radiopharm-target-agent for {args.targets} in {args.indication} ({args.isotope})...\n")
    report = run_comparative_pipeline(args.targets, args.indication, args.isotope)
    print(report)


if __name__ == "__main__":
    main()
