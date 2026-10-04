"""Détecteur de doublons exacts, SANS mutation — DN2C (SPEC §3). CLI
``--racine R`` imprime un JSON (groupes sha256, "vides") via Garde (DN2A) ;
racine « / » ou HOME -> rc 2, zéro écriture."""
import argparse
import collections
import hashlib
import json
import os
import sys
from pathlib import Path
from .chemins import Garde, RefusChemin, dans_le_nuage

def _empreinte(chemin):
    with open(chemin, "rb") as entree:
        return hashlib.file_digest(entree, "sha256").hexdigest()

def _balayer(racine, garde):
    candidats, vides, nuage = [], 0, 0
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(sous)
        for nom in sorted(noms):
            brut = Path(dossier) / nom
            try:
                garde.verifier(brut)
                st = brut.stat()
            except (OSError, RefusChemin):
                continue
            if dans_le_nuage(st):  # pas sur ce disque : le lire le téléchargerait
                nuage += 1
                continue
            if st.st_size == 0:
                vides += 1
                continue
            candidats.append((brut, st.st_size))
    tailles = collections.Counter(t for _, t in candidats)  # taille unique : aucun doublon possible, jamais lu
    fichiers = [(b.relative_to(racine).as_posix(), _empreinte(b)) for b, t in candidats if tailles[t] > 1]
    groupes_bruts = {}
    for chemin, empreinte in fichiers:
        groupes_bruts.setdefault(empreinte, []).append(chemin)
    groupes = sorted(
        ({"empreinte": e, "membres": sorted(m), "conserve": sorted(m)[0]}
         for e, m in groupes_bruts.items() if len(m) >= 2),
        key=lambda g: g["empreinte"])
    return groupes, vides, nuage

def detecter(racine, garde):
    return _balayer(racine, garde)[0]

def principal(argv=None):
    analyseur = argparse.ArgumentParser(prog="savespace_drive.doublons")
    analyseur.add_argument("--racine", type=Path, required=True)
    args = analyseur.parse_args(argv)
    interdits = {os.path.realpath("/")}
    if os.environ.get("HOME"):
        interdits.add(os.path.realpath(os.environ["HOME"]))
    brut = str(args.racine)
    if not brut.strip() or os.path.realpath(brut) in interdits:
        print(f"doublons : refus — racine interdite : {brut}", file=sys.stderr)
        return 2
    racine = Path(os.path.realpath(brut))
    groupes, vides, nuage = _balayer(racine, Garde([racine]))
    print(json.dumps({"groupes": groupes, "vides": vides, "nuage_seulement": nuage}, sort_keys=True, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(principal())
