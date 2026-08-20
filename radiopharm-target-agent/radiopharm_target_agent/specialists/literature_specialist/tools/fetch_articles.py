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
Tool for querying PubMed via NCBI Entrez E-utilities with exponential backoff,
species labeling, and structured dosimetric parameter extraction.
"""

import os
import re
from datetime import datetime, timezone
from typing import Any
from Bio import Entrez, Medline
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from radiopharm_target_agent.guards import validate_pmid
from radiopharm_target_agent.schemas import LiteratureFinding, SourceRef

# Setup Entrez authentication & rate limit parameters
Entrez.email = os.getenv("NCBI_EMAIL", "radiopharm-agent@google.com")
if os.getenv("NCBI_API_KEY"):
    Entrez.api_key = os.getenv("NCBI_API_KEY")

# Regex pattern for absorbed dose quantification (e.g. 0.45 Gy/GBq, 1.2 Gy/GBq)
DOSE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:Gy\s*/\s*GBq|mGy\s*/\s*MBq|Gy\s*per\s*GBq)",
    re.IGNORECASE,
)
ORR_PATTERN = re.compile(
    r"(?:\bORR\b|overall response rate|objective response rate)(?:\s*\([^)]*\))?\s*(?:of|was|is|:|=)?\s*(\d+(?:\.\d+)?\s*%)",
    re.IGNORECASE,
)
PFS_PATTERN = re.compile(
    r"(?:\bPFS\b|progression[- ]free survival|median PFS)(?:\s*\([^)]*\))?\s*(?:of|was|is|:|=)?\s*(\d+(?:\.\d+)?\s*(?:months|mo|weeks|days))",
    re.IGNORECASE,
)
OS_PATTERN = re.compile(
    r"(?:\bOS\b|overall survival|median OS)(?:\s*\([^)]*\))?\s*(?:of|was|is|:|=)?\s*(\d+(?:\.\d+)?\s*(?:months|mo|weeks|years))",
    re.IGNORECASE,
)

# Species word boundary regexes
MOUSE_REGEX = re.compile(
    r"\b(?:mouse|mice|murine|xenograft|athymic|scid)\b", re.IGNORECASE
)
RAT_REGEX = re.compile(
    r"\b(?:rats?|wistar|sprague-dawley)\b", re.IGNORECASE
)
NHP_REGEX = re.compile(
    r"\b(?:non-human primate|cynomolgus|macaque|rhesus|monkeys?)\b",
    re.IGNORECASE,
)
HUMAN_REGEX = re.compile(
    r"\b(?:patients?|human|clinical trial|men|women|cohort)\b", re.IGNORECASE
)
IN_VITRO_REGEX = re.compile(
    r"\b(?:in vitro|cell lines?|binding assay|micromolar|kd\s*=)\b",
    re.IGNORECASE,
)


def detect_species(text: str) -> str:
    """Classifies model species from article title and abstract using exact word boundaries."""
    # Check human first if explicit clinical trial/patient terminology
    has_mouse = bool(MOUSE_REGEX.search(text))
    has_rat = bool(RAT_REGEX.search(text))
    has_nhp = bool(NHP_REGEX.search(text))
    has_human = bool(HUMAN_REGEX.search(text))
    has_in_vitro = bool(IN_VITRO_REGEX.search(text))

    if has_mouse and not has_human:
        return "mouse"
    if has_mouse and has_human and "xenograft" in text.lower():
        return "mouse"
    if has_rat and not has_human:
        return "rat"
    if has_nhp:
        return "non_human_primate"
    if has_human:
        return "human"
    if has_mouse:
        return "mouse"
    if has_rat:
        return "rat"
    if has_in_vitro:
        return "in_vitro"
    return "human"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
def _esearch_pubmed(query: str, retmax: int = 5) -> list[str]:
    handle = Entrez.esearch(
        db="pubmed", sort="relevance", term=query, retmax=retmax
    )
    record = Entrez.read(handle)
    handle.close()
    return record.get("IdList", [])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
def _efetch_pubmed(pmids: list[str]) -> list[dict[str, Any]]:
    fetch_handle = Entrez.efetch(
        db="pubmed", id=",".join(pmids), rettype="medline", retmode="text"
    )
    records = list(Medline.parse(fetch_handle))
    fetch_handle.close()
    return records


def fetch_pubmed_articles(
    search_query: str,
    max_results: int = 4,
) -> str:
    """
    Searches PubMed for radiopharmaceutical literature, dosimetry, and efficacy evidence.

    Args:
        search_query: Search keywords (e.g., 'FOLH1 Lu-177 dosimetry prostate cancer').
        max_results: Max number of articles to return (default 4).

    Returns:
        Structured summary with PMIDs, species tags, dosimetry metrics, and abstracts.
    """
    try:
        pmids = _esearch_pubmed(search_query, retmax=max_results)
    except Exception as e:
        return f"An error occurred while searching PubMed for '{search_query}': {e}"

    if not pmids:
        return (
            f"No PubMed articles found for query: '{search_query}'. (0 results)"
        )

    try:
        records = _efetch_pubmed(pmids)
    except Exception as e:
        return f"Failed to fetch PubMed records for PMIDs {pmids}: {e}"

    output_lines = [
        f"### PubMed Literature Findings (Query: '{search_query}')",
        f"Found {len(records)} relevant peer-reviewed articles:\n",
    ]

    for i, record in enumerate(records):
        pmid = pmids[i] if i < len(pmids) else "N/A"
        title = record.get("TI", "No title available")
        abstract = record.get("AB", "No abstract available")
        combined_text = f"{title} {abstract}"

        species_label = detect_species(combined_text)

        # Detect clinical & dosimetric endpoints
        orr_match = ORR_PATTERN.search(combined_text)
        pfs_match = PFS_PATTERN.search(combined_text)
        os_match = OS_PATTERN.search(combined_text)
        dose_matches = DOSE_PATTERN.findall(combined_text)

        endpoints = []
        if orr_match:
            endpoints.append(f"ORR: {orr_match.group(1)}")
        if pfs_match:
            endpoints.append(f"PFS: {pfs_match.group(1)}")
        if os_match:
            endpoints.append(f"OS: {os_match.group(1)}")
        if dose_matches:
            endpoints.append(
                f"Absorbed Dose Mentioned: {', '.join(dose_matches[:3])} Gy/GBq"
            )

        endpoint_str = (
            f"   - **Reported Endpoints:** {'; '.join(endpoints)}\n"
            if endpoints
            else ""
        )

        output_lines.append(
            f"**{i+1}. [PMID:{pmid}]** {title}\n"
            f"   - **Species:** `{species_label}`\n"
            f"{endpoint_str}"
            f"   - **Abstract Excerpt:** {abstract[:500]}...\n"
        )

    return "\n".join(output_lines)
