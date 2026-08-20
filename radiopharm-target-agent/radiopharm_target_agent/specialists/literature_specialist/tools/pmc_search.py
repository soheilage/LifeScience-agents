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
Tool for searching PubMed Central (PMC) and extracting full-text XML articles.
"""

import os
import xml.etree.ElementTree as ET
from Bio import Entrez
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

Entrez.email = os.getenv("NCBI_EMAIL", "radiopharm-agent@google.com")
if os.getenv("NCBI_API_KEY"):
    Entrez.api_key = os.getenv("NCBI_API_KEY")


def extract_text_from_element(element: ET.Element | None) -> str:
    """Recursively extracts clean text from an XML element."""
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
def search_pmc_by_title(title_query: str, max_results: int = 1) -> str:
    """
    Searches PubMed Central for an article and extracts full body text from the XML.

    Args:
        title_query: Title, topic, or search terms to search PMC.
        max_results: Max number of results (default 1).

    Returns:
        Structured string with article title, PMCID, and full text body.
    """
    try:
        search_handle = Entrez.esearch(
            db="pmc", term=title_query, retmax=max_results
        )
        search_results = Entrez.read(search_handle)
        search_handle.close()

        id_list = search_results.get("IdList", [])
        if not id_list:
            return f"No open-access full-text results found on PubMed Central for: '{title_query}'."

        pmc_id = id_list[0]

        fetch_handle = Entrez.efetch(db="pmc", id=pmc_id, retmode="xml")
        xml_data = fetch_handle.read()
        fetch_handle.close()

        root = ET.fromstring(xml_data)
        article = root.find(".//article")
        if article is None:
            return f"PMC{pmc_id} retrieved, but article XML root structure could not be parsed."

        title_el = article.find(".//article-title")
        title = (
            extract_text_from_element(title_el)
            if title_el is not None
            else "Unknown title"
        )

        body = article.find(".//body")
        full_text = extract_text_from_element(body)

        if not full_text:
            return f"Full text body not available in open-access XML for PMC{pmc_id}: '{title}'."

        return (
            f"### PMC Full-Text Article: [PMC{pmc_id}]\n"
            f"**Title:** {title}\n\n"
            f"**Body Excerpt:**\n{full_text[:5000]}\n"
        )

    except Exception as e:
        return f"An error occurred during PMC retrieval for '{title_query}': {e}"
