#!/usr/bin/env python3
"""Faux rclone pour les tests et les captures : aucun réseau, aucun compte. L'état du « drive » est un JSON posé à côté
du script (rclone.json) : fichiers, espace, corbeille, appels reçus. Une commande inconnue répond 99 : le code ne
peut appeler que ce qui est prévu (lsjson, about, delete, config create/delete). config create imprime un FAUX jeton, comme le
vrai rclone imprime la configuration : il ne doit jamais ressortir ailleurs."""
import configparser, json, os, sys, time
from pathlib import Path

ETAT = Path(__file__).resolve().with_name("rclone.json")
JETON = "JETON-SECRET-ne-doit-jamais-sortir"


def principal(a):
    e = json.loads(ETAT.read_text()) if ETAT.exists() else {}
    e.setdefault("appels", []).append({"argv": a, "env": sorted(k for k in os.environ if k.startswith("RCLONE_"))})
    entree = sys.stdin.read().splitlines() if "-" in a else None
    rc, fichiers = 0, e.setdefault("fichiers", [])
    if a[:2] == ["config", "create"] and e.get("bloque"):  # navigateur jamais validé : attend sans fin
        e["pid"] = os.getpid()
        ETAT.write_text(json.dumps(e))
        time.sleep(120)
    if a[:2] == ["config", "delete"]:
        conf, c = a[a.index("--config") + 1], configparser.ConfigParser(interpolation=None)
        c.read(conf)
        c.remove_section(a[2])
        with open(conf, "w") as f:
            c.write(f)
    elif a[:2] == ["config", "create"]:
        conf = Path(a[a.index("--config") + 1])
        conf.write_text(f"[{a[2]}]\ntype = {a[3]}\ntoken = {{\"access_token\":\"{JETON}\"}}\n")
        print(conf.read_text())
        print(f"NOTICE: jeton {JETON}", file=sys.stderr)
        rc = e.get("rc_connexion", 0)
    elif a[0] == "lsjson" and not e.get("panne"):
        h = a[a.index("--hash-type") + 1]
        print(json.dumps([{"Path": f["p"], "Name": f["p"].rsplit("/", 1)[-1], "Size": f["t"], "IsDir": False,
                           **({"Hashes": {h: f["h"]}} if f.get("h") else {})}
                          for f in fichiers if entree is None or f["p"] in entree]))
    elif a[0] == "about" and not e.get("panne"):
        print(json.dumps(e.get("about", {})))
    elif a[0] == "delete":
        jetes = [f for f in fichiers if f["p"] in entree]
        e["corbeille"] = e.get("corbeille", []) + jetes
        e["fichiers"] = [f for f in fichiers if f not in jetes]
    else:
        print(f"ERROR: panne ou commande non prévue ; jeton {JETON}", file=sys.stderr)
        rc = 99
    ETAT.write_text(json.dumps(e))
    return rc


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
