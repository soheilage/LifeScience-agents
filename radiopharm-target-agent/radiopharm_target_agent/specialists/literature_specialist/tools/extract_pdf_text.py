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
Tool for downloading and extracting raw text from PDF documents using pypdf.
Replaces deprecated PyPDF2 (Phase 1 requirement).
"""

import io
import pypdf
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, requests.exceptions.Timeout)
    ),
    reraise=False,
)
def _download_pdf_content(pdf_url: str) -> bytes:
    response = requests.get(
        pdf_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()
    return response.content


def extract_pdf_text_from_url(pdf_url: str) -> str:
    """
    Downloads a PDF document from a direct URL and extracts its full text content using pypdf.

    Args:
        pdf_url: The direct URL to a research paper or clinical report PDF.

    Returns:
        The extracted plain text content of the PDF document.
    """
    clean_url = pdf_url.strip()
    if not clean_url.lower().endswith(".pdf") and "pdf" not in clean_url.lower():
        return f"Error: URL '{clean_url}' does not appear to point to a PDF document."

    try:
        content = _download_pdf_content(clean_url)
        pdf_file = io.BytesIO(content)
        reader = pypdf.PdfReader(pdf_file)

        extracted_pages = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                extracted_pages.append(page_text)

        full_text = "\n\n".join(extracted_pages)
        if not full_text.strip():
            return (
                f"Successfully downloaded PDF ({len(reader.pages)} pages), but could not extract selectable text. "
                "The PDF may be scanned/image-based."
            )

        return full_text

    except Exception as e:
        return f"Failed to download or parse PDF from {pdf_url}: {e}"
