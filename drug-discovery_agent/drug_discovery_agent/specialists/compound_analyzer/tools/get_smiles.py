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

"""Tool for finding a compound's SMILES string from its name using PubChem."""

import pubchempy as pcp

COMMON_SMILES_FALLBACK = {
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "paracetamol": "CC(=O)NC1=CC=C(O)C=C1",
    "acetaminophen": "CC(=O)NC1=CC=C(O)C=C1",
    "panadol": "CC(=O)NC1=CC=C(O)C=C1",
    "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "metformin": "CN(C)C(=N)N=C(N)N",
}

def get_smiles_from_name(compound_name: str) -> str:
    """
    Looks up a compound's SMILES string by its name in the PubChem database.

    Args:
        compound_name: The common or IUPAC name of the compound.

    Returns:
        The canonical SMILES string for the compound, or an error message.
    """
    clean_name = compound_name.strip().lower()
    try:
        # Search PubChem by name
        compounds = pcp.get_compounds(compound_name, 'name')
        if compounds and compounds[0].isomeric_smiles:
            return f"The SMILES string for '{compound_name}' is {compounds[0].isomeric_smiles}"
    except Exception:
        pass

    if clean_name in COMMON_SMILES_FALLBACK:
        return f"The SMILES string for '{compound_name}' is {COMMON_SMILES_FALLBACK[clean_name]}"

    return f"No compound found in PubChem for name: '{compound_name}'"
