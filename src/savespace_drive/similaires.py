"""Similaires à blanc — SaveSpace Drive, jalon DN5A (SPEC §1) : groupes = composantes connexes des paires
« même taille d'octets ET |écart| maximal octet par octet ≤ seuil » (échelle 0-255, défaut 4) ; lecture
seule, stdlib seule, aucun binaire appelé (czkawka_cli écarté par écrit, CANDIDATS.md DN5A)."""
import json, os, sys
from argparse import ArgumentParser
from savespace_drive.chemins import COMPOSANTES_NOIRES

EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp", ".ppm", ".mp4", ".mov", ".mkv", ".avi"}


def _principal(argv=None):
    """CLI : python -m savespace_drive.similaires DOSSIER [--seuil N] — rc 0, ou refus rc 2."""
    a = ArgumentParser(description="Similaires à blanc (lecture seule) : groupes quasi identiques, aucune action.")
    a.add_argument("--seuil", type=int, default=4, help="écart maximal octet/octet dans [0, 255] (défaut 4)"); a.add_argument("dossier", help="dossier à parcourir ; refus rc 2 si absent ou racine « / »")
    args = a.parse_args(argv)
    if not 0 <= args.seuil <= 255 or os.path.realpath(args.dossier) == "/" or not os.path.isdir(args.dossier):
        print(f"similaires : refus — seuil {args.seuil} hors [0, 255], dossier absent ou racine « / »", file=sys.stderr)
        return 2
    fichiers = {}
    for courant, sous, noms in os.walk(args.dossier):
        sous[:] = [d for d in sous if d not in COMPOSANTES_NOIRES]
        for chemin in (os.path.join(courant, n) for n in noms if os.path.splitext(n)[1].lower() in EXTENSIONS):
            fichiers[os.path.relpath(chemin, args.dossier).replace(os.sep, "/")] = (os.path.getsize(chemin), open(chemin, "rb").read())
    groupes, restants = [], sorted(fichiers)
    while restants:
        depart = restants.pop(0)
        pile, groupe = [depart], [depart]
        while pile:
            taille_x, octets_x = fichiers[x := pile.pop()]
            for y in [y for y in restants if fichiers[y][0] == taille_x and max((abs(p - q) for p, q in zip(octets_x, fichiers[y][1])), default=0) <= args.seuil]: restants.remove(y); groupe.append(y); pile.append(y)
        if len(groupe) > 1: groupes.append(sorted(groupe))
    for n, g in enumerate(groupes, 1): print(f"g{n} : {', '.join(g)}")
    print(json.dumps({"groupes": groupes, "racine": args.dossier, "seuil": args.seuil}, sort_keys=True)); return 0

if __name__ == "__main__": sys.exit(_principal())
