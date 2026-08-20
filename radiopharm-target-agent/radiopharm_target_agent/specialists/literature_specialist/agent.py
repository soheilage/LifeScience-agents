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

"""Literature Specialist LlmAgent definition."""

import os
from google.adk.agents import LlmAgent
from . import prompt
from .tools.extract_pdf_text import extract_pdf_text_from_url
from .tools.fetch_articles import fetch_pubmed_articles
from .tools.pmc_search import search_pmc_by_title
from .tools.summarize_paper import summarize_paper

MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro")

literature_specialist = LlmAgent(
    name="literature_specialist",
    model=MODEL,
    description="Gathers and extracts peer-reviewed literature, clinical dosimetry, and target biology evidence with strict source citation.",
    instruction=prompt.LITERATURE_SPECIALIST_PROMPT,
    tools=[
        fetch_pubmed_articles,
        search_pmc_by_title,
        extract_pdf_text_from_url,
        summarize_paper,
    ],
)
