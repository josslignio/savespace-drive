"""Remote local « banc » — SaveSpace Drive, jalon DN0C (ROADMAP DN0, SPEC §5).

Écrit --racine/rclone.conf : section [savespace-banc], type = alias,
remote = chemin absolu CANONIQUE résolu de --racine (realpath : « .. » et
liens symboliques résolus). Contenu 100 % déterministe (aucun horodatage) :
deux exécutions → octets identiques. Refus net (rc=2, zéro écriture) si la
racine est « / » ou le HOME (env) du processus. Aucun binaire exécuté, aucun
réseau : le conf est prêt pour un futur lancement réel, rien n'est lancé.
"""
import argparse
import json
import os
import sys
from pathlib import Path

NOM_CONF = "rclone.conf"
NOM_REMOTE = "savespace-banc"


def _refuser(message):
    """Sort en erreur avant TOUTE écriture disque."""
    print(f"remote_local : refus — {message}", file=sys.stderr)
    raise SystemExit(2)


def _contenu_conf(racine_absolue):
    """Renvoie les octets déterministes du conf (aucune variation entre runs)."""
    return (f"[{NOM_REMOTE}]\n"
            "type = alias\n"
            f"remote = {racine_absolue}\n").encode("utf-8")


def principal(argv=None):
    analyseur = argparse.ArgumentParser(
        prog="savespace_drive.remote_local",
        description="Écrit le conf rclone du remote local « banc » (DN0C).")
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
    (dossier / NOM_CONF).write_bytes(_contenu_conf(racine))
    print(json.dumps({"config": NOM_CONF, "remote": NOM_REMOTE},
                     sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
