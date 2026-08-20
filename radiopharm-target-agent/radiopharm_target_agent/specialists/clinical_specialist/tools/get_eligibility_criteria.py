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
Tool for fetching and parsing trial eligibility criteria from ClinicalTrials.gov API v2.

Extracts patient inclusion criteria, baseline imaging cutoffs (SUV thresholds),
and prior line requirements.
"""

import re
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from radiopharm_target_agent.guards import validate_nct_id

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Common radiopharm imaging cutoff regexes
SUV_PATTERN = re.compile(
    r"(?:SUVmax|SUV|standardized uptake value)\s*(?:>=|>|equal to or greater than|of at least)?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
SCAN_POSITIVITY_PATTERN = re.compile(
    r"(?:PSMA|SSTR|somatostatin|target|PET)\s*(?:positive|avidity|uptake|positivity)",
    re.IGNORECASE,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, requests.exceptions.Timeout)
    ),
    reraise=False,
)
def _fetch_eligibility_api(trial_id: str) -> dict | None:
    url = f"{BASE_URL}/{trial_id}?fields=protocolSection.eligibilityModule,protocolSection.identificationModule"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def get_eligibility_criteria(trial_id: str) -> str:
    """
    Fetches clinical trial eligibility criteria from ClinicalTrials.gov API v2 for a given NCT ID.
    Extracts baseline imaging positivity thresholds (e.g. SUVmax cutoffs) and pre-conditions.

    Args:
        trial_id: The NCT identifier (e.g., 'NCT03511664').

    Returns:
        Structured summary with baseline imaging thresholds and raw criteria text.
    """
    clean_id = trial_id.strip().upper()
    if not validate_nct_id(clean_id):
        return f"Error: Invalid NCT ID format '{trial_id}'. Expected format 'NCTxxxxxxxx' (e.g. NCT03511664)."

    try:
        data = _fetch_eligibility_api(clean_id)
    except Exception as e:
        return f"Failed to retrieve eligibility criteria for {clean_id}: {e}"

    if not data or not data.get("protocolSection"):
        return f"Trial ID '{clean_id}' not found or has no protocol data."

    protocol = data["protocolSection"]
    eligibility = protocol.get("eligibilityModule", {})
    criteria_text = eligibility.get("eligibilityCriteria", "")

    if not criteria_text:
        return f"No eligibility criteria text available for trial {clean_id}."

    # Extract imaging thresholds
    imaging_findings = []
    suv_match = SUV_PATTERN.search(criteria_text)
    if suv_match:
        imaging_findings.append(
            f"Baseline SUV Threshold: SUV >= {suv_match.group(1)}"
        )

    if SCAN_POSITIVITY_PATTERN.search(criteria_text):
        imaging_findings.append(
            "Diagnostic scan positivity / avidity required for enrollment."
        )

    threshold_summary = (
        "\n- " + "\n- ".join(imaging_findings)
        if imaging_findings
        else "No specific SUV cutoff explicitly extracted."
    )

    return (
        f"### Eligibility Criteria for Trial [{clean_id}]\n\n"
        f"**Extracted Baseline Imaging Pre-conditions:**{threshold_summary}\n\n"
        f"**Full Eligibility Text (excerpt):**\n"
        f"{criteria_text[:2500]}\n"
    )
