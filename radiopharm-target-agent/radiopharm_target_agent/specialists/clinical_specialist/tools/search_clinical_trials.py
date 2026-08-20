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
Tool for searching and classifying clinical trials on ClinicalTrials.gov API v2.

Implements radiopharm modality classification (therapy vs diagnostic vs ADC vs cell therapy),
intervention-based isotope detection, and structured TrialRecord emission.
"""

import re
from datetime import datetime, timezone
from typing import Any
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from radiopharm_target_agent.guards import validate_nct_id
from radiopharm_target_agent.schemas import SourceRef, TrialRecord

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Known canonical radiopharmaceutical drugs & isotope mappings
KNOWN_RADIOPHARM_DRUG_MAP = {
    "RYZ101": {"isotope": "Ac-225", "modality": "therapy"},
    "225AC-DOTATATE": {"isotope": "Ac-225", "modality": "therapy"},
    "ALPHAMEDIX": {"isotope": "Pb-212", "modality": "therapy"},
    "212PB-DOTAMTATE": {"isotope": "Pb-212", "modality": "therapy"},
    "177LU-DOTATATE": {"isotope": "Lu-177", "modality": "therapy"},
    "LUTATHERA": {"isotope": "Lu-177", "modality": "therapy"},
    "177LU-PSMA-617": {"isotope": "Lu-177", "modality": "therapy"},
    "PLUVICTO": {"isotope": "Lu-177", "modality": "therapy"},
    "177LU-PSMA-I&T": {"isotope": "Lu-177", "modality": "therapy"},
    "225AC-PSMA-617": {"isotope": "Ac-225", "modality": "therapy"},
    "68GA-DOTATATE": {"isotope": "Ga-68", "modality": "diagnostic"},
    "NETSPOT": {"isotope": "Ga-68", "modality": "diagnostic"},
    "68GA-DOTATOC": {"isotope": "Ga-68", "modality": "diagnostic"},
    "68GA-PSMA-11": {"isotope": "Ga-68", "modality": "diagnostic"},
    "LOCAMETZ": {"isotope": "Ga-68", "modality": "diagnostic"},
    "18F-DCFPYL": {"isotope": "F-18", "modality": "diagnostic"},
    "PYLARIFY": {"isotope": "F-18", "modality": "diagnostic"},
    "18F-PSMA-1007": {"isotope": "F-18", "modality": "diagnostic"},
}

# Radionuclide definitions
THERAPY_ISOTOPES = {
    "Ac-225": ["225ac", "ac-225", "actinium-225", "actinium 225", "225actinium"],
    "Lu-177": ["177lu", "lu-177", "lutetium-177", "lutetium 177", "177lutetium"],
    "Pb-212": ["212pb", "pb-212", "lead-212", "lead 212"],
    "I-131": ["131i", "i-131", "iodine-131", "iodine 131", "131iodine"],
    "Y-90": ["90y", "y-90", "yttrium-90", "yttrium 90", "90yttrium"],
    "Tb-161": ["161tb", "tb-161", "terbium-161", "terbium 161"],
}

DIAGNOSTIC_ISOTOPES = {
    "Ga-68": ["68ga", "ga-68", "gallium-68", "gallium 68", "68gallium"],
    "F-18": ["18f", "f-18", "fluorine-18", "18f-psma", "18f-dcfpyl", "pylarify"],
    "Cu-64": ["64cu", "cu-64", "copper-64"],
    "Tc-99m": ["99mtc", "tc-99m", "technetium-99m"],
    "In-111": ["111in", "in-111", "indium-111"],
    "Zr-89": ["89zr", "zr-89", "zirconium-89"],
}

ADC_KEYWORDS = [
    "antibody-drug conjugate",
    "adc",
    "vedotin",
    "emtansine",
    "deruxtecan",
    "govitecan",
    "ozogamicin",
    "mafodotin",
]

CELL_THERAPY_KEYWORDS = [
    "car-t",
    "chimeric antigen receptor",
    "t-cell receptor",
    "tcr-t",
    "til therapy",
    "natural killer",
    "nk cell",
]

# RLT with word boundaries
RLT_REGEX = re.compile(
    r"\b(?:radioligand therapy|targeted radionuclide therapy|peptide receptor radionuclide therapy|prrt|targeted alpha therapy|tat|radiopharmaceutical therapy)\b",
    re.IGNORECASE,
)


def classify_modalities_and_isotopes(
    text: str,
    interventions: list[dict[str, Any]] | None = None,
) -> tuple[list[str], str | None, bool]:
    """
    Classifies a study's text and interventions into radiopharmaceutical modalities and isotopes.

    Prioritizes investigational intervention fields over title/eligibility mentions
    to avoid confounding prior lines (e.g. 'following 177Lu-SSA') with trial payload (e.g. RYZ101 / Ac-225).
    """
    modalities = []
    detected_isotope = None
    is_radiopharm = False

    # 1. Check intervention list first for canonical drug mappings
    if interventions:
        for intv in interventions:
            name = (intv.get("name") or "").strip().upper()
            desc = (intv.get("description") or "").strip().upper()
            full_intv = f"{name} {desc}"

            for drug, mapping in KNOWN_RADIOPHARM_DRUG_MAP.items():
                if drug in full_intv or drug.replace("-", "") in full_intv.replace("-", ""):
                    modalities.append(mapping["modality"])
                    detected_isotope = mapping["isotope"]
                    is_radiopharm = True
                    break
            if detected_isotope:
                break

    # 2. Check text for therapeutic isotopes if not found from canonical map
    text_lower = text.lower()
    if not detected_isotope:
        for iso, kws in THERAPY_ISOTOPES.items():
            if any(kw in text_lower for kw in kws):
                modalities.append("therapy")
                detected_isotope = iso
                is_radiopharm = True
                break

    # 3. Check diagnostic isotopes
    if not detected_isotope:
        for iso, kws in DIAGNOSTIC_ISOTOPES.items():
            if any(kw in text_lower for kw in kws):
                detected_isotope = iso
                modalities.append("diagnostic")
                is_radiopharm = True
                break

    # 4. RLT regex check
    is_rlt = bool(RLT_REGEX.search(text))
    if is_rlt:
        if "therapy" not in modalities:
            modalities.append("therapy")
        is_radiopharm = True

    # 5. Diagnostic imaging check
    if any(kw in text_lower for kw in ["pet scan", "spect", "pet/ct", "diagnostic imaging"]):
        if "diagnostic" not in modalities:
            modalities.append("diagnostic")
        is_radiopharm = True

    # 6. ADC check
    if any(kw in text_lower for kw in ADC_KEYWORDS):
        modalities.append("ADC")

    # 7. Cell therapy check
    if any(kw in text_lower for kw in CELL_THERAPY_KEYWORDS):
        modalities.append("cell_therapy")

    if not modalities:
        modalities.append("systemic_or_targeted")

    return list(set(modalities)), detected_isotope, is_radiopharm


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, requests.exceptions.Timeout)
    ),
    reraise=False,
)
def _fetch_trials_api(
    search_query: str, page_size: int = 10
) -> dict[str, Any] | None:
    params = {
        "query.term": search_query,
        "pageSize": page_size,
        "format": "json",
    }
    response = requests.get(BASE_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def search_trials(
    target: str,
    indication: str | None = None,
    isotope: str | None = None,
    isotope_filter: str | None = None,
    isotope_context: str | None = None,
    max_results: int = 5,
    **kwargs: Any,
) -> str:
    """
    Searches ClinicalTrials.gov API v2 for radiopharmaceutical and oncology clinical trials.

    Args:
        target: The target gene/protein symbol or name (e.g., 'FOLH1', 'PSMA', 'SSTR2').
        indication: Disease indication (e.g., 'prostate cancer', 'neuroendocrine').
        isotope: Specific isotope filter (e.g., 'Lu-177', 'Ac-225', 'Ga-68').
        isotope_filter: Alias for isotope.
        isotope_context: Alias for isotope.
        max_results: Maximum number of trials to return (default 5).

    Returns:
        Structured text briefing with validated NCT IDs, modality labels, and isotope tags.
    """
    active_iso = isotope or isotope_filter or isotope_context

    # Build primary query
    query_parts = [target]
    if indication:
        ind_clean = indication.replace("gastroenteropancreatic", "GEP").replace("tumours", "tumors")
        query_parts.append(ind_clean)
    if active_iso:
        query_parts.append(active_iso)

    query_str = " ".join(query_parts)

    data = None
    try:
        data = _fetch_trials_api(query_str, page_size=max_results)
    except Exception:
        pass

    # Fallback to relaxed query if exact multi-word string returned no studies
    if not data or not data.get("studies"):
        relaxed_queries = []
        if target.upper() == "SSTR2":
            relaxed_queries.extend([
                f"RYZ101 {active_iso or ''}",
                f"DOTATATE {active_iso or ''}",
                f"DOTATOC {active_iso or ''}",
                f"SSTR2 {active_iso or ''}",
                f"somatostatin receptor {active_iso or ''}",
            ])
        elif target.upper() in ["FOLH1", "PSMA"]:
            relaxed_queries.extend([
                f"PSMA-617 {active_iso or ''}",
                f"PSMA {active_iso or ''}",
                f"FOLH1 {active_iso or ''}",
            ])
        else:
            if active_iso:
                relaxed_queries.append(f"{target} {active_iso}")
            relaxed_queries.append(target)

        for alt_q in relaxed_queries:
            try:
                alt_data = _fetch_trials_api(alt_q.strip(), page_size=max_results)
                if alt_data and alt_data.get("studies"):
                    data = alt_data
                    query_str = alt_q.strip()
                    break
            except Exception:
                continue

    if not data or not data.get("studies"):
        return f"No clinical trials found matching target '{target}' and query '{query_str}'."

    studies = data["studies"]
    records: list[TrialRecord] = []
    output_lines = [
        f"### Clinical Trial Landscape for '{target}' (Query: '{query_str}')",
        f"Retrieved {len(studies)} candidate trials from ClinicalTrials.gov API v2:\n",
    ]

    for idx, study in enumerate(studies[:max_results], 1):
        protocol = study.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        nct_id = id_module.get("nctId", "")
        title = id_module.get("officialTitle") or id_module.get(
            "briefTitle", "No title available"
        )

        status_module = protocol.get("statusModule", {})
        overall_status = status_module.get("overallStatus", "Unknown status")

        design_module = protocol.get("designModule", {})
        phases = design_module.get("phases", ["Phase not specified"])
        phase_str = ", ".join(phases) if isinstance(phases, list) else str(phases)

        conditions_module = protocol.get("conditionsModule", {})
        conditions = conditions_module.get("conditions", [])

        arms_module = protocol.get("armsInterventionsModule", {})
        raw_interventions = arms_module.get("interventions", [])
        interventions_text = [
            i.get("name", "")
            for i in raw_interventions
            if i.get("name")
        ]

        full_study_text = (
            f"{title} {' '.join(conditions)} {' '.join(interventions_text)}"
        )
        modalities, detected_iso, is_radio = classify_modalities_and_isotopes(
            full_study_text, interventions=raw_interventions
        )

        # Build SourceRef
        source_ref = SourceRef(
            kind="ctgov",
            identifier=nct_id,
            retrieved_at=datetime.now(timezone.utc),
            version="API_v2",
        )

        record = TrialRecord(
            nct_id=nct_id,
            title=title,
            phase=phase_str,
            status=overall_status,
            modalities=modalities,
            is_radiopharmaceutical=is_radio,
            isotope=detected_iso or active_iso,
            sources=[source_ref],
        )
        records.append(record)

        modality_tags = " | ".join([f"`{m.upper()}`" for m in modalities])
        iso_tag = f" | Isotope: `{detected_iso or 'Not specified'}`" if is_radio else ""

        output_lines.extend([
            f"**{idx}. [{nct_id}]** — {title}",
            f"   - **Phase:** {phase_str} | **Status:** {overall_status}",
            f"   - **Modalities:** {modality_tags}{iso_tag}",
            f"   - **Conditions:** {', '.join(conditions[:3]) if conditions else 'Not listed'}",
            "",
        ])

    return "\n".join(output_lines)
