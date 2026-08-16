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

"""Tool for identifying a compound from its SMILES string using PubChem."""

import pubchempy as pcp

COMMON_COMPOUNDS_BY_SMILES = {
    "CC(=O)OC1=CC=CC=C1C(=O)O": {
        "common_name": "Aspirin",
        "iupac_name": "2-acetyloxybenzoic acid",
        "formula": "C9H8O4",
    },
    "CC(=O)NC1=CC=C(O)C=C1": {
        "common_name": "Acetaminophen",
        "iupac_name": "N-(4-hydroxyphenyl)acetamide",
        "formula": "C8H9NO2",
    },
    "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O": {
        "common_name": "Ibuprofen",
        "iupac_name": "2-[4-(2-methylpropyl)phenyl]propanoic acid",
        "formula": "C13H18O2",
    },
    "CN(C)C(=N)N=C(N)N": {
        "common_name": "Metformin",
        "iupac_name": "3-(diaminomethylidene)-1,1-dimethylguanidine",
        "formula": "C4H11N5",
    },
}

def get_compound_info(smiles_string: str) -> str:
    """
    Looks up a compound by its SMILES string in PubChem.

    Args:
        smiles_string: The SMILES string representation of the drug.

    Returns:
        A string with the compound's name and other details, or an error message.
    """
    clean_smiles = smiles_string.strip()
    try:
        # Search PubChem by SMILES string
        compounds = pcp.get_compounds(clean_smiles, 'smiles')
        if compounds:
            compound = compounds[0]
            common_name = compound.synonyms[0] if compound.synonyms else (compound.iupac_name or "N/A")
            iupac_name = compound.iupac_name or "N/A"
            formula = compound.molecular_formula or "N/A"

            return (
                f"Successfully identified compound from SMILES '{clean_smiles}':\n"
                f"- Common Name: {common_name}\n"
                f"- IUPAC Name: {iupac_name}\n"
                f"- Molecular Formula: {formula}"
            )
    except Exception:
        pass

    # Check fallback dictionary for known common compounds if PubChem is unavailable
    if clean_smiles in COMMON_COMPOUNDS_BY_SMILES:
        info = COMMON_COMPOUNDS_BY_SMILES[clean_smiles]
        return (
            f"Successfully identified compound from SMILES '{clean_smiles}':\n"
            f"- Common Name: {info['common_name']}\n"
            f"- IUPAC Name: {info['iupac_name']}\n"
            f"- Molecular Formula: {info['formula']}"
        )

    return f"Could not identify compound for SMILES: '{clean_smiles}' (PubChem unavailable)"