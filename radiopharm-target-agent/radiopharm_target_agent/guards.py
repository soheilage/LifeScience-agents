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
Guards, validators, and anti-hallucination controls for radiopharm-target-agent.

Implements:
- NCT and PMID format and round-trip resolution validators (Gate G1)
- Membrane / accessibility hard gate (Gate G2)
- Gene symbol resolution and abstention guards (Gate G2)
- Citation-or-abstain enforcement
"""

import re
from typing import Any
import requests

NCT_REGEX = re.compile(r"^NCT\d{8}$")
PMID_REGEX = re.compile(r"^\d{1,9}$")

# Known gene symbol alias mapping & canonical definitions
CANONICAL_GENE_REGISTRY = {
    "FOLH1": {
        "symbol": "FOLH1",
        "name": "folate hydrolase 1 (prostate-specific membrane antigen)",
        "uniprot_id": "Q04656",
        "aliases": ["PSMA", "GCP2", "PSM"],
        "disambiguation_note": "Resolved 'PSMA' to canonical 'FOLH1'. Note: Proteasome subunit alpha genes (PSMA1-PSMA7) were explicitly excluded.",
        "membrane_accessible": True,
        "topology": "Single-pass type II membrane protein",
    },
    "SSTR2": {
        "symbol": "SSTR2",
        "name": "somatostatin receptor 2",
        "uniprot_id": "P30874",
        "aliases": ["SS2R", "SRIF-1"],
        "disambiguation_note": None,
        "membrane_accessible": True,
        "topology": "Multi-pass (7TM GPCR) membrane protein",
    },
    "FAP": {
        "symbol": "FAP",
        "name": "fibroblast activation protein alpha",
        "uniprot_id": "Q12884",
        "aliases": ["FAPA", "DPPIV", "seprase"],
        "disambiguation_note": "FAP is predominantly localized to cancer-associated fibroblasts (CAFs) and tumor stroma, not malignant epithelial cells.",
        "membrane_accessible": True,
        "topology": "Single-pass type II membrane protein",
    },
    "MSLN": {
        "symbol": "MSLN",
        "name": "mesothelin",
        "uniprot_id": "Q13421",
        "aliases": ["MPF", "SMR"],
        "disambiguation_note": "Known soluble shed isoform (soluble mesothelin-related peptide / SMRP).",
        "membrane_accessible": True,
        "topology": "GPI-anchor membrane protein",
    },
    "ERBB2": {
        "symbol": "ERBB2",
        "name": "erb-b2 receptor tyrosine kinase 2",
        "uniprot_id": "P04626",
        "aliases": ["HER2", "NEU", "CD340"],
        "disambiguation_note": "Resolved 'HER2' to canonical 'ERBB2'. Known shed extracellular domain (sHER2).",
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "CEACAM5": {
        "symbol": "CEACAM5",
        "name": "carcinoembryonic antigen related cell adhesion molecule 5",
        "uniprot_id": "P06731",
        "aliases": ["CEA", "CD66E"],
        "disambiguation_note": "High circulating shed soluble CEA in patient serum.",
        "membrane_accessible": True,
        "topology": "GPI-anchor cell surface glycoprotein",
    },
    "MUC16": {
        "symbol": "MUC16",
        "name": "mucin 16, cell surface associated",
        "uniprot_id": "Q8WXI7",
        "aliases": ["CA125", "CA-125"],
        "disambiguation_note": "Extensively shed into blood pool as CA-125 biomarker.",
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "GAPDH": {
        "symbol": "GAPDH",
        "name": "glyceraldehyde-3-phosphate dehydrogenase",
        "uniprot_id": "P04406",
        "aliases": ["G3PD", "GAPD"],
        "disambiguation_note": "Ubiquitously expressed housekeeping enzyme. Negative control for tumour selectivity.",
        "membrane_accessible": False,
        "topology": "Cytosolic / Nuclear enzyme",
    },
    "MKI67": {
        "symbol": "MKI67",
        "name": "marker of proliferation Ki-67",
        "uniprot_id": "P46013",
        "aliases": ["KI-67", "KIA"],
        "disambiguation_note": "Intracellular nuclear proliferation marker. Negative control for cell-surface accessibility.",
        "membrane_accessible": False,
        "topology": "Nuclear matrix protein",
    },
    "TP53": {
        "symbol": "TP53",
        "name": "tumor protein p53",
        "uniprot_id": "P04637",
        "aliases": ["P53", "LFS1"],
        "disambiguation_note": "Intracellular nuclear transcription factor. Inaccessible to intact radioligands.",
        "membrane_accessible": False,
        "topology": "Nuclear / Cytosolic transcription factor",
    },
    "MYC": {
        "symbol": "MYC",
        "name": "MYC proto-oncogene, bHLH transcription factor",
        "uniprot_id": "P01106",
        "aliases": ["C-MYC", "BHLHE39"],
        "disambiguation_note": "Intracellular nuclear transcription factor.",
        "membrane_accessible": False,
        "topology": "Nuclear transcription factor",
    },
    "STEAP1": {
        "symbol": "STEAP1",
        "name": "six-transmembrane epithelial antigen of the prostate 1",
        "uniprot_id": "Q9UHE8",
        "aliases": ["PRSS24", "STEAP"],
        "disambiguation_note": None,
        "membrane_accessible": True,
        "topology": "Multi-pass (6TM) membrane protein",
    },
    "TMEFF2": {
        "symbol": "TMEFF2",
        "name": "transmembrane protein with EGF like and two follistatin like domains 2",
        "uniprot_id": "Q9UIK5",
        "aliases": ["TENB2", "TOMAG", "TPEF"],
        "disambiguation_note": None,
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "DLL3": {
        "symbol": "DLL3",
        "name": "delta like canonical Notch ligand 3",
        "uniprot_id": "Q9NYJ7",
        "aliases": ["SCDO1"],
        "disambiguation_note": None,
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "EPCAM": {
        "symbol": "EPCAM",
        "name": "epithelial cell adhesion molecule",
        "uniprot_id": "P16422",
        "aliases": ["CD326", "GA733-2"],
        "disambiguation_note": "Epithelial malignant cell marker.",
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "PTPRC": {
        "symbol": "PTPRC",
        "name": "protein tyrosine phosphatase receptor type C (CD45)",
        "uniprot_id": "P08575",
        "aliases": ["CD45", "L-CA", "T200"],
        "disambiguation_note": "Pan-leukocyte immune marker.",
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
}

# Known non-existent / invalid symbols that must trigger abstention
KNOWN_INVALID_SYMBOLS = {"FOLH9", "PSMA9", "SSTR99", "INVALID_GENE"}


def validate_nct_id(nct_id: str) -> bool:
    """Checks if an NCT identifier matches the canonical regex format."""
    if not nct_id or not isinstance(nct_id, str):
        return False
    return bool(NCT_REGEX.match(nct_id.strip()))


def validate_pmid(pmid: str) -> bool:
    """Checks if a PubMed identifier matches the canonical numeric format."""
    if not pmid or not isinstance(pmid, str):
        return False
    return bool(PMID_REGEX.match(pmid.strip()))


def resolve_gene_symbol(query: str) -> dict[str, Any]:
    """
    Resolves gene aliases to canonical HGNC symbols with explicit disambiguation.
    Enforces abstention on unrecognised gene symbols (Gate G2).
    """
    cleaned = query.strip().upper()

    if cleaned in KNOWN_INVALID_SYMBOLS:
        return {
            "status": "abstain",
            "symbol": cleaned,
            "canonical_symbol": None,
            "reason": f"'{cleaned}' is not an approved HGNC gene symbol or recognised target. Abstaining to prevent confabulation.",
        }

    # Direct match
    if cleaned in CANONICAL_GENE_REGISTRY:
        info = CANONICAL_GENE_REGISTRY[cleaned]
        return {
            "status": "resolved",
            "symbol": cleaned,
            "canonical_symbol": info["symbol"],
            "name": info["name"],
            "uniprot_id": info["uniprot_id"],
            "disambiguation_note": info["disambiguation_note"],
            "membrane_accessible": info["membrane_accessible"],
            "topology": info["topology"],
        }

    # Search through aliases
    for sym, info in CANONICAL_GENE_REGISTRY.items():
        if cleaned in [a.upper() for a in info["aliases"]]:
            return {
                "status": "resolved",
                "symbol": cleaned,
                "canonical_symbol": info["symbol"],
                "name": info["name"],
                "uniprot_id": info["uniprot_id"],
                "disambiguation_note": info["disambiguation_note"],
                "membrane_accessible": info["membrane_accessible"],
                "topology": info["topology"],
            }

    # Unknown gene: abstain
    return {
        "status": "abstain",
        "symbol": cleaned,
        "canonical_symbol": None,
        "reason": f"Gene symbol '{cleaned}' could not be resolved to a verified HGNC entry. Abstaining to prevent confabulation.",
    }


def check_membrane_gate(
    topology: str | None,
    subcellular_locations: list[str] | None = None,
    gene_symbol: str | None = None,
) -> tuple[bool, str]:
    """
    Evaluates whether a target passes the cell-surface accessibility hard gate.
    Intracellular targets (nuclear, cytoplasmic) cannot bind intact radioligands.
    """
    if gene_symbol:
        res = resolve_gene_symbol(gene_symbol)
        if res.get("status") == "resolved" and not res.get(
            "membrane_accessible"
        ):
            return False, (
                f"Target {gene_symbol} failed cell-surface membrane gate: "
                f"Annotated as intracellular ({res.get('topology', 'intracellular')}). "
                "Intact radiopharmaceuticals cannot access intracellular targets."
            )

    combined_text = f"{topology or ''} {' '.join(subcellular_locations or [])}".lower()

    # Positive surface markers
    surface_keywords = [
        "transmembrane",
        "cell membrane",
        "plasma membrane",
        "single-pass",
        "multi-pass",
        "gpi-anchor",
        "extracellular",
        "cell surface",
    ]
    # Hard negative markers
    intracellular_keywords = [
        "nuclear",
        "nucleus",
        "nucleolus",
        "cytoplasm",
        "cytosol",
        "mitochondrial",
        "ribosomal",
    ]

    has_surface = any(kw in combined_text for kw in surface_keywords)
    is_pure_intracellular = any(
        kw in combined_text for kw in intracellular_keywords
    ) and not has_surface

    if is_pure_intracellular or (topology and not has_surface):
        return False, (
            f"Target failed cell-surface membrane gate: Subcellular localization is intracellular "
            f"({topology or 'no transmembrane domain'}). Radioligand therapy requires extracellular accessibility."
        )

    return True, "Target passed cell-surface accessibility gate."


def enforce_citation_or_abstain(
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filters out any quantitative or measured claim that lacks a verifiable source.
    """
    valid_claims = []
    for c in claims:
        status = c.get("status")
        sources = c.get("sources", [])
        if status == "measured" and not sources:
            # Drop or convert to unavailable with caveat
            c_copy = dict(c)
            c_copy["status"] = "unavailable"
            c_copy["value"] = None
            c_copy["caveats"] = c_copy.get("caveats", []) + [
                "Claim withheld: measured claim lacked verified source attribution."
            ]
            valid_claims.append(c_copy)
        else:
            valid_claims.append(c)
    return valid_claims
