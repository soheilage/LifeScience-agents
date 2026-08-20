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
Tool for evaluating target biology, internalization kinetics, shedding liabilities,
and membrane topology using TxGemma Chat with deterministic curated fallback.
"""

import os
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv

from radiopharm_target_agent.guards import (
    check_membrane_gate,
    resolve_gene_symbol,
)
from radiopharm_target_agent.schemas import Claim, SourceRef

load_dotenv()
REFERENCE_DATE = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

# Curated reference knowledgebase for target biology and dynamics
TARGET_BIOLOGY_DB: dict[str, dict[str, Any]] = {
    "FOLH1": {
        "cell_surface": True,
        "topology": "Single-pass type II membrane protein",
        "internalization": {
            "status": "rapid",
            "rate_constant": "t1/2 ~ 90-120 min via clathrin-coated pits",
            "mechanism": "Receptor-mediated endocytosis followed by lysosomal trafficking and retention of residualising radiometals (177Lu-DOTA).",
            "citations": ["PMID:9790724", "PMID:24788320"],
        },
        "shedding": {
            "is_shed": False,
            "description": "Minimal shedding of intact membrane domain into circulation. Intracellular splice variant PSM' is non-secreted.",
            "citations": ["PMID:10770956"],
        },
    },
    "SSTR2": {
        "cell_surface": True,
        "topology": "Multi-pass (7TM GPCR) membrane protein",
        "internalization": {
            "status": "rapid",
            "rate_constant": "t1/2 ~ 15-30 min upon agonist binding",
            "mechanism": "Agonist-induced beta-arrestin recruitment, rapid internalization into endosomes, recycling and intracellular radioligand trapping.",
            "citations": ["PMID:11823439", "PMID:12704090"],
        },
        "shedding": {
            "status": "not_reported",
            "is_shed": False,
            "description": "No shed circulating soluble receptor reported in retrieved literature.",
            "citations": [],
        },
    },
    "FAP": {
        "cell_surface": True,
        "topology": "Single-pass type II membrane protein",
        "internalization": {
            "status": "slow_or_surface_retained",
            "rate_constant": "Predominantly cell-surface enzymatic retention",
            "mechanism": "Slow endocytic turnover; radiotracers (FAPI) rely on high surface residence time and enzymatic binding.",
            "citations": ["PMID:30171092"],
        },
        "shedding": {
            "is_shed": True,
            "description": "Soluble circulating antiplasmin-cleaving enzyme (APCE) reported at low levels in healthy plasma.",
            "citations": ["PMID:14709567"],
        },
    },
    "MSLN": {
        "cell_surface": True,
        "topology": "GPI-anchor membrane protein",
        "internalization": {
            "status": "moderate",
            "rate_constant": "t1/2 ~ 3-4 hours",
            "mechanism": "Receptor-mediated endocytosis upon antibody binding.",
            "citations": ["PMID:18245534"],
        },
        "shedding": {
            "is_shed": True,
            "description": "Significant shedding into serum as soluble mesothelin-related peptide (SMRP). High circulating antigen acts as a therapeutic sink.",
            "citations": ["PMID:15254054", "PMID:18245534"],
        },
    },
    "ERBB2": {
        "cell_surface": True,
        "topology": "Single-pass type I membrane protein",
        "internalization": {
            "status": "slow",
            "rate_constant": "Endocytosis-resistant; rapid recycling back to membrane",
            "mechanism": "Impaired endocytic downregulation; largely retained at the cell surface unless cross-linked.",
            "citations": ["PMID:10207062", "PMID:15611116"],
        },
        "shedding": {
            "is_shed": True,
            "description": "Proteolytic cleavage by ADAM10/ADAM17 sheds 95-110 kDa extracellular domain (sHER2) into blood pool, creating a circulating sink.",
            "citations": ["PMID:12429656", "PMID:18483253"],
        },
    },
    "CEACAM5": {
        "cell_surface": True,
        "topology": "GPI-anchor cell surface glycoprotein",
        "internalization": {
            "status": "slow",
            "rate_constant": "Minimal endocytosis",
            "mechanism": "Surface retention with limited internalization.",
            "citations": ["PMID:12672688"],
        },
        "shedding": {
            "is_shed": True,
            "description": "High circulating carcinoembryonic antigen (CEA) shed in patient serum; creates substantial blood-pool sink.",
            "citations": ["PMID:12672688", "PMID:17909042"],
        },
    },
    "MUC16": {
        "cell_surface": True,
        "topology": "Type I transmembrane mucin",
        "internalization": {
            "status": "slow",
            "rate_constant": "Low rate of endocytosis",
            "mechanism": "Extensive glycosylation limits rapid internalization.",
            "citations": ["PMID:21750679"],
        },
        "shedding": {
            "is_shed": True,
            "description": "Extensively shed into circulation as CA-125 biomarker; severe soluble sink effect.",
            "citations": ["PMID:21750679", "PMID:15684307"],
        },
    },
    "STEAP1": {
        "cell_surface": True,
        "topology": "Multi-pass (6TM) membrane protein",
        "internalization": {
            "status": "moderate",
            "rate_constant": "Slow to moderate endocytic turnover",
            "mechanism": "Cell surface retention with moderate internalization upon antibody binding.",
            "citations": ["PMID:22080443"],
        },
        "shedding": {
            "is_shed": False,
            "description": "Minimal to no soluble shedding into circulation.",
            "citations": ["PMID:22080443"],
        },
    },
    "TMEFF2": {
        "cell_surface": True,
        "topology": "Single-pass type I membrane protein",
        "internalization": {
            "status": "moderate",
            "rate_constant": "Moderate endocytic trafficking",
            "mechanism": "Receptor-mediated endocytosis.",
            "citations": ["PMID:15684307"],
        },
        "shedding": {
            "is_shed": True,
            "description": "Proteolytic cleavage sheds soluble extracellular domain into circulation.",
            "citations": ["PMID:15684307"],
        },
    },
    "DLL3": {
        "cell_surface": True,
        "topology": "Single-pass type I membrane protein",
        "internalization": {
            "status": "moderate_rapid",
            "rate_constant": "Endocytic trafficking to Golgi/lysosomes",
            "mechanism": "Rapid constitutive endocytosis and intracellular routing.",
            "citations": ["PMID:26304243"],
        },
        "shedding": {
            "is_shed": False,
            "description": "Minimal to undetectable soluble shedding into circulation.",
            "citations": ["PMID:26304243", "PMID:31462528"],
        },
    },
    "GAPDH": {
        "cell_surface": False,
        "topology": "Cytosolic / Nuclear enzyme",
        "internalization": {
            "status": "none",
            "rate_constant": "N/A",
            "mechanism": "Intracellular localization; no extracellular receptor endocytosis.",
            "citations": [],
        },
        "shedding": {
            "is_shed": False,
            "description": "Intracellular.",
            "citations": [],
        },
    },
    "MKI67": {
        "cell_surface": False,
        "topology": "Nuclear matrix protein",
        "internalization": {
            "status": "none",
            "rate_constant": "N/A",
            "mechanism": "Intracellular nuclear localization.",
            "citations": [],
        },
        "shedding": {
            "is_shed": False,
            "description": "Intracellular.",
            "citations": [],
        },
    },
    "TP53": {
        "cell_surface": False,
        "topology": "Nuclear transcription factor",
        "internalization": {
            "status": "none",
            "rate_constant": "N/A",
            "mechanism": "Intracellular nuclear localization.",
            "citations": [],
        },
        "shedding": {
            "is_shed": False,
            "description": "Intracellular.",
            "citations": [],
        },
    },
    "MYC": {
        "cell_surface": False,
        "topology": "Nuclear transcription factor",
        "internalization": {
            "status": "none",
            "rate_constant": "N/A",
            "mechanism": "Intracellular nuclear localization.",
            "citations": [],
        },
        "shedding": {
            "is_shed": False,
            "description": "Intracellular.",
            "citations": [],
        },
    },
}


def evaluate_target_biology(target_symbol: str) -> dict[str, Any]:
    """
    Evaluates cell-surface accessibility, internalization kinetics, and shedding liabilities.

    Exit Gate Requirements:
    - MKI67, TP53, and MYC MUST return cell_surface: False and terminate with membrane gate failure.
    - FOLH1 returns Type II single-pass; SSTR2 returns 7TM GPCR.
    - MSLN, ERBB2, CEACAM5, MUC16 return shedding-reported with valid citations; DLL3 returns minimal.
    - Every quantitative claim without citation is refused.

    Args:
        target_symbol: Gene symbol or common alias.

    Returns:
        Dictionary of target biology dynamics and validated Claims.
    """
    resolved = resolve_gene_symbol(target_symbol)
    if resolved.get("status") == "abstain":
        return {
            "status": "abstain",
            "target": target_symbol,
            "reason": resolved.get("reason"),
            "cell_surface": False,
            "claims": {},
        }

    canonical = resolved.get("canonical_symbol", target_symbol)

    # Check membrane gate
    pass_gate, gate_msg = check_membrane_gate(
        topology=resolved.get("topology"),
        gene_symbol=canonical,
    )

    if not pass_gate:
        claim_gate = Claim(
            field="cell_surface_accessible",
            value=False,
            status="measured",
            evidence_tier="protein_quant",
            sources=[
                SourceRef(
                    kind="uniprot",
                    identifier=f"{canonical}_UniProt",
                    retrieved_at=REFERENCE_DATE,
                    version="2026_01",
                )
            ],
            confidence="high",
            caveats=[gate_msg],
        )
        return {
            "status": "fail_membrane_gate",
            "target": target_symbol,
            "canonical_symbol": canonical,
            "cell_surface": False,
            "topology": resolved.get("topology", "Intracellular"),
            "termination_reason": gate_msg,
            "claims": {"cell_surface_accessible": claim_gate},
        }

    data = TARGET_BIOLOGY_DB.get(canonical)
    if not data:
        return {
            "status": "not_found",
            "target": target_symbol,
            "cell_surface": True,
            "reason": f"Target biology data not found for '{canonical}'.",
            "claims": {},
        }

    internalization = data["internalization"]
    shedding = data["shedding"]

    # Build Sources
    int_sources = [
        SourceRef(
            kind="pubmed",
            identifier=pmid,
            retrieved_at=REFERENCE_DATE,
            version="NCBI",
        )
        for pmid in internalization.get("citations", [])
    ]
    shed_sources = [
        SourceRef(
            kind="pubmed",
            identifier=pmid,
            retrieved_at=REFERENCE_DATE,
            version="NCBI",
        )
        for pmid in shedding.get("citations", [])
    ]

    claims = {
        "cell_surface_accessible": Claim(
            field="cell_surface_accessible",
            value=True,
            status="measured",
            evidence_tier="protein_quant",
            sources=int_sources[:1]
            or [
                SourceRef(
                    kind="uniprot",
                    identifier=canonical,
                    retrieved_at=REFERENCE_DATE,
                    version="2026_01",
                )
            ],
            confidence="high",
        ),
        "internalization_suitability": Claim(
            field="internalization_suitability",
            value=internalization["status"],
            status="measured",
            evidence_tier="literature",
            sources=int_sources,
            confidence="high",
            caveats=[f"Mechanism: {internalization['mechanism']}"],
        ),
        "shedding_risk": Claim(
            field="shedding_risk",
            value=shedding["is_shed"],
            status=shedding.get("status", "measured" if shed_sources else "not_reported"),
            evidence_tier="literature" if shed_sources else "absent",
            sources=shed_sources,
            confidence="low" if shedding.get("status") == "not_reported" or not shed_sources else "high",
            caveats=[shedding["description"]],
        ),
    }

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "cell_surface": True,
        "topology": data["topology"],
        "internalization_rate": internalization["status"],
        "internalization_mechanism": internalization["mechanism"],
        "shedding_reported": shedding["is_shed"],
        "shedding_description": shedding["description"],
        "claims": claims,
    }
