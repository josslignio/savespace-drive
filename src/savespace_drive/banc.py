"""Banc d'arborescence synthétique — SaveSpace Drive, jalon DN0A (ROADMAP DN0, SPEC §5).

Crée sous --racine, de façon déterministe (random.Random(--graine)) : groupes de
doublons exacts (« Copie de … », « …(1)… »), gros fichiers creux (truncate), faux
caches Library/Caches/…, faux fichiers protégés (.ssh/id_rsa, .git/HEAD), puis un
manifeste.json (chemins relatifs à la racine + tailles, JSON trié). Refus net
(rc != 0, zéro écriture) si la racine est « / » ou le HOME (env) du processus.
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path


def _refuser(message):
    """Sort en erreur avant TOUTE écriture disque."""
    print(f"banc : refus — {message}", file=sys.stderr)
    raise SystemExit(2)


def _ecrire(racine, relatif, contenu=None, taille=None):
    """Écrit racine/relatif : octets, ou fichier creux de `taille` (truncate)."""
    if relatif.is_absolute() or ".." in relatif.parts:
        _refuser(f"chemin hors racine : {relatif}")
    cible = racine / relatif
    cible.parent.mkdir(parents=True, exist_ok=True)
    if taille is None:
        cible.write_bytes(contenu)
    else:
        with open(cible, "wb") as sortie:
            sortie.truncate(taille)
    return {"chemin": relatif.as_posix(), "taille": cible.stat().st_size}


def generer(graine, racine):
    """Construit l'arborescence du banc ; renvoie le manifeste (une entrée par catégorie)."""
    rng = random.Random(graine)
    decalage = graine % 1_000_000
    manifeste = {"doublons": [], "gros": [], "caches": [], "proteges": []}
    for i in range(3):
        base = f"rapport_{i}_{rng.randrange(1_000_000):06d}"
        contenu = f"contenu synthetique groupe {i} graine {graine} sel {rng.randrange(10**9)}".encode()
        noms = (f"{base}.pdf", f"Copie de {base}.pdf", f"{base}(1).pdf")
        manifeste["doublons"].append(
            [_ecrire(racine, Path("documents") / nom, contenu) for nom in noms])
    for i, mo in enumerate((1024, 512, 256)):
        nom = f"archive_{i}_{rng.randrange(1000):03d}.bin"
        manifeste["gros"].append(
            _ecrire(racine, Path("gros") / nom, taille=mo * 1_000_000 + decalage))
    for app in ("com.exemple.app", "com.savespace.banc", "org.test.jeu"):
        relatif = Path("Library/Caches") / app / "cache.db"
        manifeste["caches"].append(
            _ecrire(racine, relatif, contenu=b"0" * rng.randrange(100, 900)))
    manifeste["caches"].append(
        _ecrire(racine, Path("Library/Logs/savespace-banc.log"),
                contenu=f"banc graine {graine}\n".encode()))
    cle = b"-----BEGIN FAUX PRIVATE KEY-----\ndonnee synthetique DN0A\n-----END FAUX PRIVATE KEY-----\n"
    manifeste["proteges"].append(_ecrire(racine, Path(".ssh/id_rsa"), contenu=cle))
    manifeste["proteges"].append(
        _ecrire(racine, Path(".git/HEAD"), contenu=b"ref: refs/heads/main\n"))
    return manifeste


def principal(argv=None):
    analyseur = argparse.ArgumentParser(
        prog="savespace_drive.banc",
        description="Génère le banc d'arborescence synthétique SaveSpace Drive (DN0A).")
    analyseur.add_argument("--graine", type=int, required=True,
                           help="entier pilotant la génération déterministe")
    analyseur.add_argument("--racine", type=Path, required=True,
                           help="dossier cible ; refusé si « / » ou le HOME du processus")
    args = analyseur.parse_args(argv)
    interdits = {os.path.realpath("/")}
    if os.environ.get("HOME"):
        interdits.add(os.path.realpath(os.environ["HOME"]))
    brut = str(args.racine)
    if not brut.strip():
        _refuser("racine vide")
    racine = os.path.realpath(brut)
    if racine in interdits:
        _refuser(f"racine interdite : {brut} (racines refusées : / et HOME)")
    dossier = Path(racine)
    dossier.mkdir(parents=True, exist_ok=True)
    manifeste = generer(args.graine, dossier)
    (dossier / "manifeste.json").write_text(
        json.dumps(manifeste, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    nb = sum(len(g) if isinstance(g, list) else 1
             for cat in manifeste.values() for g in cat)
    print(f"banc : {nb} fichiers sous {racine} (graine {args.graine}), manifeste.json écrit")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
