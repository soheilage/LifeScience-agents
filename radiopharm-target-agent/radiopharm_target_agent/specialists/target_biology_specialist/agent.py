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

"""Target Biology Specialist LlmAgent definition."""

import os
from google.adk.agents import LlmAgent
from . import prompt
from .tools.ligand_tractability import assess_ligand_tractability
from .tools.predict_toxicity import predict_ligand_toxicity
from .tools.txgemma_target_eval import evaluate_target_biology

MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro")

target_biology_specialist = LlmAgent(
    name="target_biology_specialist",
    model=MODEL,
    description="Evaluates target internalization dynamics, shedding liabilities, membrane topology, and binder tractability.",
    instruction=prompt.TARGET_BIOLOGY_SPECIALIST_PROMPT,
    tools=[
        evaluate_target_biology,
        assess_ligand_tractability,
        predict_ligand_toxicity,
    ],
)
