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

"""Clinical Specialist LlmAgent definition."""

import os
from google.adk.agents import LlmAgent
from . import prompt
from .tools.get_eligibility_criteria import get_eligibility_criteria
from .tools.search_clinical_trials import search_trials

MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro")

clinical_specialist = LlmAgent(
    name="clinical_specialist",
    model=MODEL,
    description="Searches ClinicalTrials.gov and extracts structured clinical trial landscape evidence for radiopharmaceuticals.",
    instruction=prompt.CLINICAL_SPECIALIST_PROMPT,
    tools=[
        search_trials,
        get_eligibility_criteria,
    ],
)
