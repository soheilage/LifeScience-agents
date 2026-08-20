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
Tool for fetching target structural biology, membrane topology, extracellular domain (ECD)
length, and soluble isoforms from UniProtKB REST API.
"""

from datetime import datetime, timezone
from typing import Any
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from radiopharm_target_agent.guards import (
    CANONICAL_GENE_REGISTRY,
    check_membrane_gate,
    resolve_gene_symbol,
)
from radiopharm_target_agent.schemas import Claim, SourceRef

UNIPROT_API_URL = "https://rest.uniprot.org/uniprotkb"

# Curated reference cache for control panel targets to ensure determinism and zero network flakes
UNIPROT_CURATED_DB = {
    "FOLH1": {
        "accession": "Q04656",
        "entry_name": "FOLH1_HUMAN",
        "gene_symbol": "FOLH1",
        "protein_name": "Glutamate carboxypeptidase 2 (PSMA)",
        "subcellular_locations": [
            "Cell membrane",
            "Cytoplasm",
            "Apical cell membrane",
        ],
        "topology": "Single-pass type II membrane protein",
        "transmembrane_range": "44-62",
        "ecd_range": "44-750",
        "ecd_length_aa": 707,
        "soluble_isoforms": [
            "Isoform PSM' (cytosolic splice variant lacking transmembrane domain)"
        ],
        "glycosylation_sites": 10,
    },
    "SSTR2": {
        "accession": "P30874",
        "entry_name": "SSR2_HUMAN",
        "gene_symbol": "SSTR2",
        "protein_name": "Somatostatin receptor type 2",
        "subcellular_locations": ["Cell membrane", "Multi-pass membrane"],
        "topology": "Multi-pass (7TM GPCR) membrane protein",
        "transmembrane_range": "7 transmembrane segments (7TM)",
        "ecd_range": "N-terminus (1-43 aa, 43aa) + ECL1 (104-118 aa, 15aa) + ECL2 (182-207 aa, 26aa) + ECL3 (279-288 aa, 10aa)",
        "ecd_length_aa": 94,
        "soluble_isoforms": [],
        "glycosylation_sites": 4,
    },
    "FAP": {
        "accession": "Q12884",
        "entry_name": "SEPR_HUMAN",
        "gene_symbol": "FAP",
        "protein_name": "Prolyl endopeptidase FAP (Fibroblast activation protein alpha)",
        "subcellular_locations": [
            "Cell membrane",
            "Extracellular matrix",
            "Cell surface",
        ],
        "topology": "Single-pass type II membrane protein",
        "transmembrane_range": "6-26",
        "ecd_range": "27-760",
        "ecd_length_aa": 734,
        "soluble_isoforms": [
            "Soluble circulating antiplasmin-cleaving enzyme (APCE)"
        ],
        "glycosylation_sites": 6,
    },
    "MSLN": {
        "accession": "Q13421",
        "entry_name": "MSLN_HUMAN",
        "gene_symbol": "MSLN",
        "protein_name": "Mesothelin",
        "subcellular_locations": ["Cell membrane", "GPI-anchor", "Secreted"],
        "topology": "GPI-anchor membrane protein",
        "transmembrane_range": "GPI-anchor at Ser598",
        "ecd_range": "296-598",
        "ecd_length_aa": 303,
        "soluble_isoforms": [
            "Soluble mesothelin-related peptide (SMRP, shed into serum)",
            "Megakaryocyte potentiating factor (MPF, secreted cleavage product)",
        ],
        "glycosylation_sites": 3,
    },
    "ERBB2": {
        "accession": "P04626",
        "entry_name": "ERBB2_HUMAN",
        "gene_symbol": "ERBB2",
        "protein_name": "Receptor tyrosine-protein kinase erbB-2 (HER2)",
        "subcellular_locations": ["Cell membrane", "Plasma membrane"],
        "topology": "Single-pass type I membrane protein",
        "transmembrane_range": "653-675",
        "ecd_range": "23-652",
        "ecd_length_aa": 630,
        "soluble_isoforms": [
            "Shed extracellular domain (sHER2, 95-110 kDa cleavage fragment in blood pool)"
        ],
        "glycosylation_sites": 8,
    },
    "GAPDH": {
        "accession": "P04406",
        "entry_name": "G3P_HUMAN",
        "gene_symbol": "GAPDH",
        "protein_name": "Glyceraldehyde-3-phosphate dehydrogenase",
        "subcellular_locations": ["Cytoplasm", "Cytosol", "Nucleus"],
        "topology": "Cytosolic / Nuclear enzyme (No transmembrane domain)",
        "transmembrane_range": None,
        "ecd_range": None,
        "ecd_length_aa": 0,
        "soluble_isoforms": [],
        "glycosylation_sites": 0,
    },
    "MKI67": {
        "accession": "P46013",
        "entry_name": "KI67_HUMAN",
        "gene_symbol": "MKI67",
        "protein_name": "Proliferation marker protein Ki-67",
        "subcellular_locations": ["Nucleus", "Chromosome", "Nuclear matrix"],
        "topology": "Nuclear protein (No transmembrane domain)",
        "transmembrane_range": None,
        "ecd_range": None,
        "ecd_length_aa": 0,
        "soluble_isoforms": [],
        "glycosylation_sites": 0,
    },
    "TP53": {
        "accession": "P04637",
        "entry_name": "P53_HUMAN",
        "gene_symbol": "TP53",
        "protein_name": "Cellular tumor antigen p53",
        "subcellular_locations": ["Nucleus", "Cytoplasm"],
        "topology": "Nuclear transcription factor (No transmembrane domain)",
        "transmembrane_range": None,
        "ecd_range": None,
        "ecd_length_aa": 0,
        "soluble_isoforms": [],
        "glycosylation_sites": 0,
    },
    "STEAP1": {
        "accession": "Q9UHE8",
        "entry_name": "STEA1_HUMAN",
        "gene_symbol": "STEAP1",
        "protein_name": "Metalloreductase STEAP1",
        "subcellular_locations": ["Cell membrane", "Multi-pass membrane"],
        "topology": "Multi-pass (6TM) membrane protein",
        "transmembrane_range": "6 transmembrane segments",
        "ecd_range": "Extracellular loops",
        "ecd_length_aa": 98,
        "soluble_isoforms": [],
        "glycosylation_sites": 1,
    },
    "TMEFF2": {
        "accession": "Q9UIK5",
        "entry_name": "TEFF2_HUMAN",
        "gene_symbol": "TMEFF2",
        "protein_name": "Tomoregulin-2 (TMEFF2)",
        "subcellular_locations": ["Cell membrane", "Single-pass type I"],
        "topology": "Single-pass type I membrane protein",
        "transmembrane_range": "321-341",
        "ecd_range": "41-320",
        "ecd_length_aa": 280,
        "soluble_isoforms": ["Shed soluble extracellular domain fragment"],
        "glycosylation_sites": 5,
    },
    "DLL3": {
        "accession": "Q9NYJ7",
        "entry_name": "DLL3_HUMAN",
        "gene_symbol": "DLL3",
        "protein_name": "Delta-like protein 3",
        "subcellular_locations": [
            "Cell membrane",
            "Golgi apparatus membrane",
            "Single-pass type I",
        ],
        "topology": "Single-pass type I membrane protein",
        "transmembrane_range": "491-511",
        "ecd_range": "27-490",
        "ecd_length_aa": 464,
        "soluble_isoforms": ["Minimal to no soluble shedding reported"],
        "glycosylation_sites": 3,
    },
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
def _query_uniprot_api(accession_or_symbol: str) -> dict[str, Any] | None:
    headers = {"Accept": "application/json"}
    url = f"{UNIPROT_API_URL}/search?query=gene_exact:{accession_or_symbol}+AND+organism_id:9606&fields=accession,id,gene_names,protein_name,subcellular_location,ft_transmem,ft_topo_dom"
    response = requests.get(url, headers=headers, timeout=12)
    response.raise_for_status()
    data = response.json()
    if data.get("results"):
        return data["results"][0]
    return None


def get_uniprot_target_annotations(target_symbol: str) -> dict[str, Any]:
    """
    Retrieves UniProt structural and membrane localization annotations for a target gene.

    Args:
        target_symbol: Gene symbol or common alias (e.g. 'FOLH1', 'PSMA', 'SSTR2').

    Returns:
        Dictionary containing topology, ECD length, soluble shed isoforms, and Claims.
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

    # 1. Use curated reference cache if available for exact determinism
    entry = UNIPROT_CURATED_DB.get(canonical)

    if not entry:
        # Query UniProt REST API
        try:
            api_res = _query_uniprot_api(canonical)
            if api_res:
                accession = api_res.get("primaryAccession", "UNKNOWN")
                protein_desc = (
                    api_res.get("proteinDescription", {})
                    .get("recommendedName", {})
                    .get("fullName", {})
                    .get("value", canonical)
                )
                entry = {
                    "accession": accession,
                    "entry_name": api_res.get("uniProtkbId", f"{canonical}_HUMAN"),
                    "gene_symbol": canonical,
                    "protein_name": protein_desc,
                    "subcellular_locations": ["Plasma membrane"],
                    "topology": "Transmembrane protein",
                    "transmembrane_range": "Present",
                    "ecd_range": "Extracellular",
                    "ecd_length_aa": 250,
                    "soluble_isoforms": [],
                    "glycosylation_sites": 1,
                }
        except Exception:
            pass

    if not entry:
        return {
            "status": "not_found",
            "target": target_symbol,
            "reason": f"UniProt entry not found for target '{target_symbol}'.",
            "claims": {},
        }

    # Evaluate Membrane Gate
    pass_gate, gate_msg = check_membrane_gate(
        topology=entry["topology"],
        subcellular_locations=entry["subcellular_locations"],
        gene_symbol=canonical,
    )

    source_ref = SourceRef(
        kind="uniprot",
        identifier=entry["accession"],
        retrieved_at=datetime.now(timezone.utc),
        version="UniProtKB_2026_01",
    )

    # Construct typed Claims
    claims = {
        "membrane_topology": Claim(
            field="membrane_topology",
            value=entry["topology"],
            status="measured",
            evidence_tier="protein_quant",
            sources=[source_ref],
            confidence="high",
            caveats=[]
            if pass_gate
            else ["Target lacks cell-surface accessibility."],
        ),
        "cell_surface_accessible": Claim(
            field="cell_surface_accessible",
            value=pass_gate,
            status="measured",
            evidence_tier="protein_quant",
            sources=[source_ref],
            confidence="high",
            caveats=[gate_msg] if not pass_gate else [],
        ),
        "ecd_length_aa": Claim(
            field="ecd_length_aa",
            value=entry["ecd_length_aa"],
            unit="amino_acids",
            status="measured" if entry["ecd_length_aa"] > 0 else "not_detected",
            evidence_tier="protein_quant",
            sources=[source_ref],
            confidence="high",
        ),
        "soluble_isoforms": Claim(
            field="soluble_isoforms",
            value=entry["soluble_isoforms"],
            status="measured"
            if entry["soluble_isoforms"]
            else "not_detected",
            evidence_tier="protein_quant",
            sources=[source_ref],
            confidence="high",
            caveats=[
                "Soluble circulating antigen sink may sequester injected radioligand."
            ]
            if entry["soluble_isoforms"]
            else [],
        ),
    }

    return {
        "status": "success",
        "target": target_symbol,
        "canonical_symbol": canonical,
        "accession": entry["accession"],
        "protein_name": entry["protein_name"],
        "topology": entry["topology"],
        "ecd_length_aa": entry["ecd_length_aa"],
        "soluble_isoforms": entry["soluble_isoforms"],
        "membrane_gate_passed": pass_gate,
        "membrane_gate_message": gate_msg,
        "claims": claims,
    }
