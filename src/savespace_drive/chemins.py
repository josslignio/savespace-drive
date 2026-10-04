"""Garde de chemins — SaveSpace Drive, jalon DN2A (SPEC §3) : appartenance par
composantes du chemin RÉSOLU (realpath), jamais startswith ; racines explicites ;
zéro écriture, zéro réseau, stdlib seule."""
from __future__ import annotations
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

COMPOSANTES_NOIRES = frozenset({".ssh", ".gnupg", ".git", "Keychains"})
SF_DATALESS = 0x40000000  # macOS : contenu resté dans le nuage (iCloud Drive…) ; stat.SF_DATALESS en Python 3.13
A_LA_DEMANDE = 0x1000 | 0x40000 | 0x400000  # Windows : OFFLINE, RECALL_ON_OPEN, RECALL_ON_DATA_ACCESS


def dans_le_nuage(chemin, st) -> bool:
    """Vrai si le contenu n'est pas sur le disque : l'ouvrir le téléchargerait. On ne l'ouvre JAMAIS (stat seul)."""
    nom = Path(chemin).name
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS or getattr(st, "st_file_attributes", 0) & A_LA_DEMANDE
                or (nom.startswith(".") and nom.endswith(".icloud")))  # « .photo.jpg.icloud » : ancien marque-place iCloud

class RefusChemin(Exception):
    pass

class Garde:
    def __init__(self, racines_autorisees: list[Path]) -> None:
        self.racines = [Path(os.path.realpath(r)) for r in racines_autorisees]

    def verifier(self, p: Path) -> None:
        r = Path(os.path.realpath(p))
        racine = next((x for x in self.racines if r.is_relative_to(x)), None)
        if racine is None:
            raise RefusChemin(f"{p} résolu en {r} : hors racines autorisées")
        if any(c in COMPOSANTES_NOIRES for c in r.relative_to(racine).parts):
            raise RefusChemin(f"{r} : composante interdite par SPEC §3")
        zones = [Path("/System"), Path("/Library"), Path("/Applications")]
        home = os.environ.get("HOME")
        if home:  # ~/Library interdit, sauf iCloud Drive (le dossier que l'utilisateur voit dans le Finder)
            lib = Path(os.path.realpath(home)) / "Library"
            if not r.is_relative_to(lib / "Mobile Documents" / "com~apple~CloudDocs"):
                zones.append(lib)
        if any(r.is_relative_to(z) for z in zones):
            raise RefusChemin(f"{r} : préfixe système interdit par SPEC §3")

def principal(argv: list[str] | None = None) -> int:
    analyseur = ArgumentParser(
        prog="savespace_drive.chemins",
        description="Garde de chemins : « OK » (rc 0) si CHEMIN vit sous une --racine, refus rc 3.")
    analyseur.add_argument("--racine", action="append", required=True, type=Path,
                           help="racine autorisée, répétable (zéro --racine → rc 2)")
    analyseur.add_argument("chemin", type=Path, help="chemin à éprouver")
    args = analyseur.parse_args(argv)
    try:
        Garde(args.racine).verifier(args.chemin)
    except RefusChemin as exc:
        print(f"chemins : refus — {exc}", file=sys.stderr)
        return 3
    print("OK")
    return 0

if __name__ == "__main__":
    sys.exit(principal())
