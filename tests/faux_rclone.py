#!/usr/bin/env python3
"""Faux rclone pour les tests et les captures : aucun réseau, aucun compte. L'état du « drive » est un JSON posé à côté
du script (rclone.json) : fichiers, espace, corbeille, appels reçus. Une commande inconnue répond 99 : le code ne
peut appeler que ce qui est prévu (lsjson, about, delete, config create/delete). config create imprime un FAUX jeton, comme le
vrai rclone imprime la configuration : il ne doit jamais ressortir ailleurs.
Rangement : lsjson voit aussi les dossiers (« dossiers » = dossiers vides explicites), --stat, backend features
(« features »), moveto (--ignore-existing respecté : sans lui, la destination est ÉCRASÉE, comme le vrai) et rmdir."""
import configparser, json, os, re, sys, time
from pathlib import Path

ETAT = Path(__file__).resolve().with_name("rclone.json")
JETON = "JETON-SECRET-ne-doit-jamais-sortir"


def principal(a):
    e = json.loads(ETAT.read_text()) if ETAT.exists() else {}
    e.setdefault("appels", []).append({"argv": a, "env": sorted(k for k in os.environ if k.startswith("RCLONE_"))})
    entree = sys.stdin.read().splitlines() if "-" in a else None
    rc, fichiers, vides = 0, e.setdefault("fichiers", []), e.setdefault("dossiers", [])
    chemins = [x.split(":", 1)[1].strip("/") for x in a if re.match(r"^[A-Za-z0-9_-]+:", x)]
    dirs = {"/".join(f["p"].split("/")[:i]) for f in fichiers for i in range(1, f["p"].count("/") + 1)} | set(vides)
    sous = lambda c, b: not b or c.startswith(b + "/")
    entree_de = lambda f, b: {"Path": f["p"][len(b) + 1 if b else 0:], "Name": f["p"].rsplit("/", 1)[-1], "Size": f["t"],
                              "ModTime": f.get("d", "2024-03-01T10:00:00Z"), "IsDir": False}
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
    elif a[0] == "lsjson" and "--stat" in a and not e.get("panne"):
        (c,) = chemins
        f = next((f for f in fichiers if f["p"] == c), None)
        rc = 0 if f or c in dirs else 3
        print(json.dumps(entree_de(f, "") if f else {"Path": c, "IsDir": True}) if not rc else "")
    elif a[0] == "lsjson" and not e.get("panne"):
        h, (b,) = (a[a.index("--hash-type") + 1] if "--hash-type" in a else None), chemins
        if b and b not in dirs:
            rc = 3
        else:
            sortie = [{**entree_de(f, b), **({"Hashes": {h: f["h"]}} if h and f.get("h") else {})}
                      for f in fichiers if sous(f["p"], b) and (entree is None or f["p"] in entree)]
            if "--files-only" not in a:
                sortie += [{"Path": d[len(b) + 1 if b else 0:], "Name": d.rsplit("/", 1)[-1], "Size": -1, "IsDir": True,
                            "ModTime": "2024-03-01T10:00:00Z"} for d in sorted(dirs) if sous(d, b) and d != b]
            print(json.dumps(sortie))
    elif a[:2] == ["backend", "features"]:
        print(json.dumps({"Name": "faux", "Features": e.get("features", {"Move": True, "DirMove": True})}))
    elif a[0] == "moveto":
        s, d = chemins
        garde = "--ignore-existing" in a
        a_bouger = [f for f in fichiers if f["p"] == s or sous(f["p"], s) and s]
        if not a_bouger and s not in vides:
            rc = 1
        for f in a_bouger:
            n = d + f["p"][len(s):]
            pris = [g for g in fichiers if g["p"] == n]
            if pris and garde:
                continue  # comme le vrai rclone : la source reste, la destination n'est pas touchée
            e["fichiers"] = fichiers = [g for g in fichiers if g not in pris]  # sans --ignore-existing : écrasée
            f["p"] = n
        e["dossiers"] = [d + v[len(s):] if v == s or sous(v, s) else v for v in vides]
    elif a[0] == "rmdir":
        (c,) = chemins
        if any(sous(f["p"], c) for f in fichiers) or any(sous(v, c) and v != c for v in vides):
            rc = 1  # comme le vrai : jamais un dossier qui n'est pas vide
        else:
            e["dossiers"] = [v for v in vides if v != c]
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
