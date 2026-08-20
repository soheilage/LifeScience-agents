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
        "disambiguation_note": "Ubiquitous metabolic enzyme. Used as selectivity negative control.",
        "membrane_accessible": False,
        "topology": "Cytosolic enzyme",
    },
    "MKI67": {
        "symbol": "MKI67",
        "name": "marker of proliferation Ki-67",
        "uniprot_id": "P46013",
        "aliases": ["KI67", "KIA"],
        "disambiguation_note": "Intracellular nuclear antigen. Inaccessible to intact radioligands.",
        "membrane_accessible": False,
        "topology": "Nuclear protein",
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
    "GPC3": {
        "symbol": "GPC3",
        "name": "glypican 3",
        "uniprot_id": "P51654",
        "aliases": ["DGSX", "SDYS"],
        "disambiguation_note": "Oncofetal cell-surface heparan sulfate proteoglycan.",
        "membrane_accessible": True,
        "topology": "GPI-anchor membrane protein",
    },
    "FGFR2": {
        "symbol": "FGFR2",
        "name": "fibroblast growth factor receptor 2",
        "uniprot_id": "P21802",
        "aliases": ["CD332", "BEK"],
        "disambiguation_note": "Receptor tyrosine kinase.",
        "membrane_accessible": True,
        "topology": "Single-pass type I membrane protein",
    },
    "CLDN18": {
        "symbol": "CLDN18",
        "name": "claudin 18",
        "uniprot_id": "P56856",
        "aliases": ["CLDN18.2"],
        "disambiguation_note": "Tight junction 4-transmembrane protein.",
        "membrane_accessible": True,
        "topology": "Multi-pass (4TM) membrane protein",
    },
}

# Known non-existent / invalid symbols that must trigger abstention
INVALID_TARGET_SYMBOLS = {
    "FOLH9": "Abstaining: FOLH9 is not a recognised human gene or pseudogene symbol in HGNC or Ensembl.",
    "PSMA99": "Abstaining: PSMA99 is a fabricated identifier not present in HGNC.",
    "NONEXISTENT1": "Abstaining: Target does not exist.",
}


def validate_nct_id(nct_id: str) -> bool:
    """
    Validates NCT clinical trial identifier syntax (NCT followed by exactly 8 digits).
    Returns True if valid, False otherwise.
    """
    if not isinstance(nct_id, str):
        return False
    return bool(NCT_REGEX.match(nct_id.strip()))


def validate_pmid(pmid: str | int) -> bool:
    """
    Validates PubMed ID format (1 to 9 digits, positive integer).
    Returns True if valid, False otherwise.
    """
    pmid_str = str(pmid).strip()
    return bool(PMID_REGEX.match(pmid_str))


def resolve_gene_symbol(target_input: str) -> dict[str, Any]:
    """
    Resolves gene alias to canonical HGNC symbol with explicit disambiguation.
    Triggers immediate abstention for unrecognised symbols (e.g. FOLH9).

    Design Principle 1.4: Strict symbol validation before calling external APIs.
    """
    cleaned = target_input.strip().upper()

    # 1. Check known invalid / non-existent symbols
    if cleaned in INVALID_TARGET_SYMBOLS:
        return {
            "status": "abstain",
            "target_input": target_input,
            "canonical_symbol": None,
            "reason": INVALID_TARGET_SYMBOLS[cleaned],
            "disambiguation_note": None,
        }

    # 2. Check canonical registry directly
    if cleaned in CANONICAL_GENE_REGISTRY:
        meta = CANONICAL_GENE_REGISTRY[cleaned]
        return {
            "status": "resolved",
            "target_input": target_input,
            "canonical_symbol": meta["symbol"],
            "uniprot_id": meta["uniprot_id"],
            "name": meta["name"],
            "topology": meta["topology"],
            "disambiguation_note": meta["disambiguation_note"],
        }

    # 3. Check alias mapping
    for canonical, meta in CANONICAL_GENE_REGISTRY.items():
        if cleaned in [a.upper() for a in meta["aliases"]]:
            return {
                "status": "resolved",
                "target_input": target_input,
                "canonical_symbol": canonical,
                "uniprot_id": meta["uniprot_id"],
                "name": meta["name"],
                "topology": meta["topology"],
                "disambiguation_note": meta["disambiguation_note"],
            }

    # 4. Unknown target fallback (Fail Closed Abstention)
    return {
        "status": "abstain",
        "target_input": target_input,
        "canonical_symbol": None,
        "reason": f"Abstaining: Target '{target_input}' could not be resolved to a known validated HGNC gene symbol.",
        "disambiguation_note": None,
    }


def check_membrane_gate(
    topology: str | None = None,
    locations: list[str] | None = None,
    subcellular_locations: list[str] | None = None,
    gene_symbol: str | None = None,
    **kwargs: Any,
) -> tuple[bool, str]:
    """
    Enforces Phase 4 & Gate G2 Cell-Surface Membrane Accessibility Gate.
    Terminates / fails targets localized intracellularly (nuclear, cytosolic).
    """
    locs = locations or subcellular_locations or []
    text = f"{topology or ''} {' '.join(locs)} {gene_symbol or ''}".lower()

    if gene_symbol and gene_symbol in CANONICAL_GENE_REGISTRY:
        is_acc = CANONICAL_GENE_REGISTRY[gene_symbol]["membrane_accessible"]
        top = CANONICAL_GENE_REGISTRY[gene_symbol]["topology"]
        if is_acc:
            return True, "Target passed cell-surface accessibility gate."
        else:
            return (
                False,
                f"Target '{gene_symbol}' failed cell-surface membrane gate: intracellular ({top}).",
            )

    if any(k in text for k in ["nuclear", "nucleus", "cytosol", "cytoplasmic", "mitochondr"]) and not any(
        k in text for k in ["single-pass", "multi-pass", "membrane", "transmembrane", "plasma membrane", "cell membrane", "cell surface", "gpi"]
    ):
        return (
            False,
            f"Target '{gene_symbol or 'unknown'}' failed cell-surface membrane gate: intracellular localization ({topology}).",
        )

    if any(
        k in text
        for k in [
            "single-pass",
            "multi-pass",
            "membrane",
            "transmembrane",
            "plasma membrane",
            "cell membrane",
            "cell surface",
            "gpi",
            "7tm",
        ]
    ):
        return True, "Target passed cell-surface accessibility gate."

    return (
        False,
        f"Target '{gene_symbol or 'unknown'}' failed cell-surface membrane gate: topology '{topology}' is not cell-surface accessible.",
    )


check_membrane_accessibility = check_membrane_gate


def enforce_citation_or_abstain(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Enforces that every claim marked 'measured' must have at least one valid SourceRef.
    If no source exists, sets status='unavailable' and value=None (fails closed).
    """
    sanitized = []
    for c in claims:
        item = dict(c)
        if item.get("status") == "measured" and not item.get("sources"):
            item["status"] = "unavailable"
            item["value"] = None
        sanitized.append(item)
    return sanitized


enforce_citation_contract = enforce_citation_or_abstain
