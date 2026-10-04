"""Commande doctor — SaveSpace Drive (DN0B ; DN0GZ ajoute --strict).
Sans drapeau : DN0B inchangé — which seul, trois clefs, rc 0 TOUJOURS, aucun
binaire exécuté, rien d'écrit. Avec --strict : chaque outil PRÉSENT est lancé
en sous-processus direct « <chemin> --version » (sans shell) ; la version lue
(premier triplet x.y.z d'entiers de la première ligne de stdout) est comparée
en tuples d'entiers aux minima RELUS À CHAQUE exécution : versions_gellees.json
près du module, ou le fichier désigné par SAVESPACE_VERSIONS. rc 0 ssi tout
outil présent a ok=true ; mini illisible => ok=false ; stderr vide, aucun réseau.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

OUTILS = [
    ("czkawka_cli", ("czkawka_cli",), "brew install czkawka"),
    ("rclone", ("rclone",), "brew install rclone"),
    ("osxphotos", ("osxphotos",), "brew install osxphotos"),
    ("dua", ("dua", "gdu"), "brew install dua-cli"),
]
_TRIPLET = re.compile(r"(\d+)\.(\d+)\.(\d+)")

def _tuple(texte):
    m = _TRIPLET.search(texte) if isinstance(texte, str) else None
    return tuple(map(int, m.groups())) if m else None

def _lue(chemin):
    try:
        premiere = subprocess.run([chemin, "--version"], capture_output=True, text=True,
                                  timeout=30).stdout.split("\n", 1)[0]
        return _tuple(premiere)
    except Exception:
        return None

def examiner(strict=False):
    minima = None
    if strict:
        cible = os.environ.get("SAVESPACE_VERSIONS") or Path(__file__).with_name("versions_gellees.json")
        try:
            minima = json.loads(Path(cible).read_text(encoding="utf-8"))["outils"]
        except Exception:
            minima = None
    etat = {}
    for nom, candidats, installer in OUTILS:
        chemin = next((c for c in map(shutil.which, candidats) if c), None)
        etat[nom] = {"present": chemin is not None, "chemin": chemin, "installer": installer}
        if strict:
            mini = minima.get(nom) if isinstance(minima, dict) else None
            ref, lu = _tuple(mini), (_lue(chemin) if chemin else None)
            etat[nom].update(version=".".join(map(str, lu)) if lu else None, version_mini=mini,
                             ok=lu is not None and ref is not None and lu >= ref)
    return {"outils": etat}

def principal(argv=None):
    strict = "--strict" in (sys.argv[1:] if argv is None else argv)
    rapport = examiner(strict=strict)
    print(json.dumps(rapport, sort_keys=True, ensure_ascii=False))
    return int(strict and not all(f["ok"] for f in rapport["outils"].values() if f["present"]))

if __name__ == "__main__":
    sys.exit(principal())
