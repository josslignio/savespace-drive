"""Socle de la suite produit : tout le code Python du dépôt se compile."""
import py_compile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def test_tout_le_code_se_compile():
    fichiers = sorted((RACINE / "src").rglob("*.py"))
    assert fichiers, "aucun code sous src/"
    for f in fichiers:
        py_compile.compile(str(f), doraise=True)
