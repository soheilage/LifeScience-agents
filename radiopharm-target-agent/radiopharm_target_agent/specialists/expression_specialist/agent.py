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

"""Expression Specialist LlmAgent definition."""

import os
from google.adk.agents import LlmAgent
from . import prompt
from .tools.cell2sentence_analyzer import analyze_single_cell_target
from .tools.hpa_gtex_expression import get_hpa_gtex_expression_profile
from .tools.oar_panel import build_oar_panel
from .tools.uniprot_annotations import get_uniprot_target_annotations

MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro")

expression_specialist = LlmAgent(
    name="expression_specialist",
    model=MODEL,
    description="Gathers quantitative tumour-vs-normal expression contrasts, single-cell deconvolution (C2S), OAR panel baselines, and UniProt membrane topology.",
    instruction=prompt.EXPRESSION_SPECIALIST_PROMPT,
    tools=[
        get_hpa_gtex_expression_profile,
        build_oar_panel,
        get_uniprot_target_annotations,
        analyze_single_cell_target,
    ],
)
