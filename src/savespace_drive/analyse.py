"""Analyse à blanc (lecture seule) — SaveSpace Drive, jalon DN1A (ROADMAP DN1, SPEC §3-4).
``python -m savespace_drive.analyse --racine DOSSIER [--top 5]`` parcourt DOSSIER en
LECTURE SEULE (os.walk + hashlib, aucun binaire appelé) et imprime sur stdout — et
rien d'autre — un JSON trié : total_octets ; doublons [{sha256, taille, chemins}]
groupes d'octets identiques de ≥ 2 fichiers, chemins triés — JAMAIS les chemins sous
.ssh/.git : rien de listé noire n'est proposé, donc un doublon réel injecté sous .ssh
ne fait pas bouger doublons ni recuperables_octets (SPEC §3) ; recuperables_octets =
Σ taille × (n−1) ; gros [{chemin, taille}] tailles décroissantes, égalité → ordre du
chemin, top N ; caches = sous Library/Caches ou Library/Logs ; proteges = sous .ssh
ou .git. Tous les chemins imprimés sont RELATIFS à DOSSIER. Refus net (rc != 0, zéro
écriture) si la racine est « / » ou le HOME (env) du processus.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def _refuser(message):
    """Sort en erreur avant TOUTE écriture disque."""
    print(f"analyse : refus — {message}", file=sys.stderr)
    raise SystemExit(2)


def _protege(chemin):
    """True si le chemin relatif passe sous .ssh ou .git (liste noire, SPEC §3)."""
    return bool({".ssh", ".git"} & set(chemin.split("/")))


def _cache(chemin):
    """True si le chemin relatif passe sous Library/Caches ou Library/Logs."""
    parties = chemin.split("/")
    return any(parties[i:i + 2] in (["Library", "Caches"], ["Library", "Logs"])
               for i in range(len(parties) - 1))


def _empreinte(chemin):
    """sha256 du fichier, lu par blocs (lecture seule, aucun fork)."""
    calcul = hashlib.sha256()
    with open(chemin, "rb") as entree:
        for bloc in iter(lambda: entree.read(1 << 20), b""):
            calcul.update(bloc)
    return calcul.hexdigest()


def analyser(racine, top):
    """Parcourt racine en lecture seule ; renvoie le rapport (chemins relatifs str)."""
    fichiers = []  # (chemin_relatif, taille, sha256 ou None si protégé : jamais groupé)
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = sorted(sous_dossiers)
        for nom in sorted(noms):
            brut = Path(dossier) / nom
            try:
                taille = brut.stat().st_size
                relatif = brut.relative_to(racine).as_posix()
                empreinte = None if _protege(relatif) else _empreinte(brut)
            except OSError:
                continue  # illisible : ignoré — l'analyse à blanc n'écrit ni ne s'arrête
            fichiers.append((relatif, taille, empreinte))
    groupes = {}
    for chemin, taille, empreinte in fichiers:
        if empreinte is not None:
            groupes.setdefault(empreinte, []).append((chemin, taille))
    doublons, recuperables = [], 0
    for empreinte, membres in groupes.items():
        if len(membres) < 2:
            continue
        recuperables += membres[0][1] * (len(membres) - 1)
        doublons.append({"sha256": empreinte, "taille": membres[0][1],
                         "chemins": sorted(chemin for chemin, _ in membres)})
    doublons.sort(key=lambda groupe: groupe["sha256"])
    gros = sorted(fichiers, key=lambda f: (-f[1], f[0]))[:max(top, 0)]
    return {
        "total_octets": sum(taille for _, taille, _ in fichiers),
        "doublons": doublons,
        "recuperables_octets": recuperables,
        "gros": [{"chemin": chemin, "taille": taille} for chemin, taille, _ in gros],
        "caches": sorted(chemin for chemin, _, _ in fichiers if _cache(chemin)),
        "proteges": sorted(chemin for chemin, _, _ in fichiers if _protege(chemin)),
    }


def principal(argv=None):
    analyseur = argparse.ArgumentParser(
        prog="savespace_drive.analyse",
        description="Analyse à blanc (lecture seule) SaveSpace Drive (DN1A).")
    analyseur.add_argument("--racine", type=Path, required=True,
                           help="dossier à analyser ; refusé si « / » ou le HOME du processus")
    analyseur.add_argument("--top", type=int, default=5,
                           help="nombre de gros fichiers listés (défaut : 5)")
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
    print(json.dumps(analyser(Path(racine), args.top), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
