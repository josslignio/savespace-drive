import json, os, sys
from argparse import ArgumentParser
from pathlib import Path
NOIRES = {".ssh", ".git"}
TYPES = {".mp4": "videos", ".mov": "videos", ".mkv": "videos", ".avi": "videos", ".zip": "archives", ".rar": "archives", ".7z": "archives", ".tar": "archives", ".gz": "archives", ".dmg": "installeurs", ".pkg": "installeurs", ".iso": "installeurs", ".bak": "sauvegardes", ".backup": "sauvegardes"}

def principal(argv=None):
    a = ArgumentParser(prog="savespace_drive.gros")
    a.add_argument("--top", type=int, default=100)
    args = a.parse_args(argv)
    if args.top <= 0:
        print("gros : --top doit être strictement positif", file=sys.stderr)
        return 2
    racine = Path(".")
    fichiers = []
    for d, dn, fn in os.walk(racine):
        dn[:] = [x for x in dn if x not in NOIRES]
        fichiers += [(Path(d, f).relative_to(racine).as_posix(), Path(d, f).stat().st_size) for f in fn]
    fichiers.sort(key=lambda t: (-t[1], t[0]))
    groupes = {}
    for chemin, taille in fichiers[: args.top]:
        groupes.setdefault(TYPES.get(Path(chemin).suffix.lower(), "autres"), []).append({"chemin": chemin, "taille": taille})
    for t in sorted(groupes):
        print(f"{t} : " + ", ".join(f"{e['chemin']} ({e['taille']} o)" for e in groupes[t]))
    print(json.dumps({"note": "tailles apparentes (fichiers creux comptés pleins)", "racine": ".", "top": args.top, "groupes": groupes}, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(principal())
