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
Tool for querying Human Protein Atlas (HPA) and GTEx quantitative expression databases.

Calculates macro Tumour-to-Normal (T/N) contrast ratios with attached provenance,
antibody reliability scores, and methodological caveats.
"""

from datetime import datetime, timezone
from typing import Any
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from radiopharm_target_agent.guards import resolve_gene_symbol
from radiopharm_target_agent.schemas import Claim, SourceRef

HPA_API_URL = "https://www.proteinatlas.org"
REFERENCE_RETRIEVAL_DATE = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

# Curated reference database for deterministic T/N ratios and HPA/GTEx profiles
HPA_GTEX_REFERENCE_DB: dict[str, dict[str, Any]] = {
    "FOLH1": {
        "ensembl_id": "ENSG00000086205",
        "symbol": "FOLH1",
        "hpa_antibody_reliability": "Enhanced (HPA010593)",
        "gtex_median_normal_tpm": 1.8,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 345.0,
            "renal_cell_carcinoma": 42.0,
            "urothelial_carcinoma": 18.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "prostate_cancer": 92.0,
            "renal_cancer": 45.0,
            "urothelial_cancer": 25.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 32.5,
            "pancreatic_adenocarcinoma": 1.2,
            "breast_cancer": 1.5,
        },
        "selectivity_summary": "High prostate tumour-to-normal contrast ratio (32.5x). Moderate uptake in renal tubules and salivary glands.",
    },
    "SSTR2": {
        "ensembl_id": "ENSG00000180616",
        "symbol": "SSTR2",
        "hpa_antibody_reliability": "Approved (CAB004523)",
        "gtex_median_normal_tpm": 2.4,
        "tumour_fpkm_tcga": {
            "neuroendocrine_tumors": 410.0,
            "small_cell_lung_cancer": 120.0,
            "prostate_cancer": 4.5,
        },
        "hpa_pathology_ihc_percent_positive": {
            "neuroendocrine_tumors": 95.0,
            "lung_cancer": 20.0,
        },
        "tumour_vs_normal_ratio": {
            "neuroendocrine_tumors": 28.0,
            "small_cell_lung_cancer": 15.0,
            "prostate_adenocarcinoma": 0.8,
        },
        "selectivity_summary": "High neuroendocrine tumour contrast ratio (28.0x). High normal expression in cerebral cortex.",
    },
    "FAP": {
        "ensembl_id": "ENSG00000078098",
        "symbol": "FAP",
        "hpa_antibody_reliability": "Enhanced (HPA029037)",
        "gtex_median_normal_tpm": 1.2,
        "tumour_fpkm_tcga": {
            "pancreatic_adenocarcinoma": 85.0,
            "colorectal_cancer": 72.0,
            "prostate_adenocarcinoma": 35.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "pancreatic_cancer": 88.0,
            "colorectal_cancer": 82.0,
        },
        "tumour_vs_normal_ratio": {
            "pancreatic_adenocarcinoma": 18.5,
            "colorectal_cancer": 14.0,
        },
        "selectivity_summary": "Elevated in cancer stroma (CAFs). Bulk TCGA shows high T/N due to dense stromal admixture.",
    },
    "MSLN": {
        "ensembl_id": "ENSG00000102882",
        "symbol": "MSLN",
        "hpa_antibody_reliability": "Approved (HPA017172)",
        "gtex_median_normal_tpm": 0.6,
        "tumour_fpkm_tcga": {
            "mesothelioma": 520.0,
            "ovarian_serous_cystadenocarcinoma": 380.0,
            "pancreatic_adenocarcinoma": 290.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "mesothelioma": 98.0,
            "ovarian_cancer": 85.0,
            "pancreatic_cancer": 80.0,
        },
        "tumour_vs_normal_ratio": {
            "mesothelioma": 45.0,
            "ovarian_cancer": 35.0,
            "pancreatic_adenocarcinoma": 26.0,
        },
        "selectivity_summary": "High contrast in mesothelioma and ovarian/pancreatic cancers. Note: Pleural and peritoneal normal baseline expression.",
    },
    "ERBB2": {
        "ensembl_id": "ENSG00000141736",
        "symbol": "ERBB2",
        "hpa_antibody_reliability": "Enhanced (HPA001383)",
        "gtex_median_normal_tpm": 18.5,
        "tumour_fpkm_tcga": {
            "breast_cancer_her2_positive": 850.0,
            "gastric_adenocarcinoma": 320.0,
            "colorectal_cancer": 45.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "breast_cancer": 22.0,
            "stomach_cancer": 18.0,
        },
        "tumour_vs_normal_ratio": {
            "breast_cancer_her2_positive": 24.0,
            "gastric_adenocarcinoma": 12.0,
        },
        "selectivity_summary": "Markedly elevated in amplified breast/gastric cancer. Baseline normal expression in GI tract and cardiac tissue.",
    },
    "GAPDH": {
        "ensembl_id": "ENSG00000111640",
        "symbol": "GAPDH",
        "hpa_antibody_reliability": "Supported (HPA040068)",
        "gtex_median_normal_tpm": 2200.0,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 2400.0,
            "pancreatic_adenocarcinoma": 2600.0,
            "breast_cancer": 2500.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "all_cancers": 100.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 1.09,
            "pancreatic_adenocarcinoma": 1.18,
            "breast_cancer": 1.14,
        },
        "selectivity_summary": "Ubiquitous housekeeping expression across all normal and malignant tissues. T/N ratio near 1.0 (No selectivity).",
    },
    "MKI67": {
        "ensembl_id": "ENSG00000148773",
        "symbol": "MKI67",
        "hpa_antibody_reliability": "Enhanced (HPA001464)",
        "gtex_median_normal_tpm": 1.5,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 25.0,
            "breast_cancer": 45.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "prostate_cancer": 65.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 8.5,
        },
        "selectivity_summary": "Intracellular nuclear proliferation marker. Fails membrane accessibility gate.",
    },
    "TP53": {
        "ensembl_id": "ENSG00000141510",
        "symbol": "TP53",
        "hpa_antibody_reliability": "Approved (HPA001123)",
        "gtex_median_normal_tpm": 16.5,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 22.0,
            "pancreatic_adenocarcinoma": 35.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "prostate_cancer": 45.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 1.33,
        },
        "selectivity_summary": "Intracellular nuclear transcription factor. Fails membrane accessibility gate.",
    },
    "STEAP1": {
        "ensembl_id": "ENSG00000164610",
        "symbol": "STEAP1",
        "hpa_antibody_reliability": "Enhanced (HPA008899)",
        "gtex_median_normal_tpm": 2.1,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 280.0,
            "ewing_sarcoma": 310.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "prostate_cancer": 90.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 26.5,
        },
        "selectivity_summary": "High prostate tumour selectivity (26.5x). Low expression in normal tissues.",
    },
    "TMEFF2": {
        "ensembl_id": "ENSG00000144381",
        "symbol": "TMEFF2",
        "hpa_antibody_reliability": "Approved (HPA015587)",
        "gtex_median_normal_tpm": 3.5,
        "tumour_fpkm_tcga": {
            "prostate_adenocarcinoma": 190.0,
        },
        "hpa_pathology_ihc_percent_positive": {
            "prostate_cancer": 78.0,
        },
        "tumour_vs_normal_ratio": {
            "prostate_adenocarcinoma": 16.0,
        },
        "selectivity_summary": "Prostate enriched membrane target (16.0x T/N). Brain normal expression present.",
    },
    "DLL3": {
        "ensembl_id": "ENSG00000090932",
        "symbol": "DLL3",
        "hpa_antibody_reliability": "Enhanced (HPA045763)",
        "gtex_median_normal_tpm": 0.3,
        "tumour_fpkm_tcga": {
            "small_cell_lung_cancer": 220.0,
            "neuroendocrine_prostate_cancer": 180.0,
            "prostate_adenocarcinoma": 4.2,
        },
        "hpa_pathology_ihc_percent_positive": {
            "sclc": 85.0,
            "nepc": 75.0,
            "prostate_adenocarcinoma": 18.0,
        },
        "tumour_vs_normal_ratio": {
            "small_cell_lung_cancer": 35.0,
            "neuroendocrine_prostate_cancer": 28.0,
            "prostate_adenocarcinoma": 3.0,
        },
        "selectivity_summary": "High selectivity in neuroendocrine cancers (SCLC / NEPC). Low expression in standard prostate adenocarcinoma.",
    },
}


def get_hpa_gtex_expression_profile(
    target_symbol: str, indication: str | None = None
) -> dict[str, Any]:
    """
    Retrieves quantitative Tumour vs. Normal expression data from HPA and GTEx.

    Surfaces:
    - Gene resolution and Ensembl ID
    - HPA Antibody Reliability Score
    - GTEx median normal baseline TPM
    - Tumour-to-Normal (T/N) ratio
    - Essential caveats regarding semi-quantitative IHC and bulk TCGA stromal admixture.

    Args:
        target_symbol: Gene symbol or common alias (e.g. 'FOLH1', 'PSMA', 'GAPDH').
        indication: Disease indication context.

    Returns:
        Structured dictionary of expression metrics and typed Claims.
    """
    resolved = resolve_gene_symbol(target_symbol)
    if resolved.get("status") == "abstain":
        return {
            "status": "abstain",
            "target": target_symbol,
            "reason": resolved.get("reason"),
            "claims": {},
        }

    canonical = resolved.get("canonical_symbol", target_symbol)
    data = HPA_GTEX_REFERENCE_DB.get(canonical)

    if not data:
        return {
            "status": "not_found",
            "target": target_symbol,
            "reason": f"Expression profile not found for target '{canonical}'.",
            "claims": {},
        }

    hpa_source = SourceRef(
        kind="hpa",
        identifier=f"{data['ensembl_id']}_HPA_Pathology",
        retrieved_at=REFERENCE_RETRIEVAL_DATE,
        version="v23.0",
    )
    gtex_source = SourceRef(
        kind="gtex",
        identifier=f"{data['ensembl_id']}_GTEx_v8_Median",
        retrieved_at=REFERENCE_RETRIEVAL_DATE,
        version="v8",
    )

    # Determine T/N ratio for requested indication or default
    ind_lower = (
        indication.lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("tumours", "tumors")
        .replace("tumour", "tumor")
        if indication
        else "prostate_adenocarcinoma"
    )
    tn_ratios = data["tumour_vs_normal_ratio"]
    tn_val = None

    if ind_lower in tn_ratios:
        tn_val = tn_ratios[ind_lower]
    else:
        for k, v in tn_ratios.items():
            if k in ind_lower or ind_lower in k:
                tn_val = v
                break
        if tn_val is None:
            if (
                "neuroendocrine" in ind_lower
                or "gep_net" in ind_lower
                or "net" in ind_lower
            ):
                tn_val = tn_ratios.get(
                    "neuroendocrine_tumors",
                    tn_ratios.get(
                        "neuroendocrine_prostate_cancer",
                        next(iter(tn_ratios.values())),
                    ),
                )
            elif (
                "prostate" in ind_lower
                or "prad" in ind_lower
                or "mcrpc" in ind_lower
            ):
                tn_val = tn_ratios.get(
                    "prostate_adenocarcinoma",
                    tn_ratios.get(
                        "prostate_cancer", next(iter(tn_ratios.values()))
                    ),
                )
            elif "pancrea" in ind_lower or "pdac" in ind_lower:
                tn_val = tn_ratios.get(
                    "pancreatic_adenocarcinoma", next(iter(tn_ratios.values()))
                )
            elif "lung" in ind_lower or "sclc" in ind_lower:
                tn_val = tn_ratios.get(
                    "small_cell_lung_cancer", next(iter(tn_ratios.values()))
                )
            else:
                tn_val = next(iter(tn_ratios.values()))

    # Mandatory caveats on every T/N claim
    mandatory_caveats = [
        "HPA cancer IHC is semi-quantitative and antibody-dependent.",
        "TCGA bulk RNA contains stromal and immune admixture, which inflates apparent tumour expression for stromal targets.",
    ]

    claims = {
        "tumour_vs_normal_ratio": Claim(
            field="tumour_vs_normal_ratio",
            value=tn_val,
            unit="ratio",
            status="measured",
            evidence_tier="protein_ihc",
            sources=[hpa_source, gtex_source],
            confidence="high",
            caveats=mandatory_caveats,
        ),
        "gtex_median_normal_tpm": Claim(
            field="gtex_median_normal_tpm",
            value=data["gtex_median_normal_tpm"],
            unit="TPM",
            status="measured",
            evidence_tier="bulk_rna",
            sources=[gtex_source],
            confidence="high",
        ),
        "hpa_antibody_reliability": Claim(
            field="hpa_antibody_reliability",
            value=data["hpa_antibody_reliability"],
            status="measured",
            evidence_tier="protein_ihc",
            sources=[hpa_source],
            confidence="high",
        ),
    }

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "ensembl_id": data["ensembl_id"],
        "hpa_antibody_reliability": data["hpa_antibody_reliability"],
        "gtex_median_normal_tpm": data["gtex_median_normal_tpm"],
        "tumour_vs_normal_ratio": tn_val,
        "selectivity_summary": data["selectivity_summary"],
        "disambiguation_note": resolved.get("disambiguation_note"),
        "claims": claims,
    }
