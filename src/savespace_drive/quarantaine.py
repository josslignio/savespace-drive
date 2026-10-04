"""savespace_drive.quarantaine : restauration depuis un manifeste gele (DN2B). Autonome, stdlib seule."""
import hashlib, json, os, sys
import time
from savespace_drive.chemins import Garde, RefusChemin

NOIRS = (".ssh", ".gnupg", ".git", "Keychains")
def _sha256(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def _garde(p, racine):
    r = os.path.realpath(p)
    return r.startswith(racine) and not (set(r.split(os.sep)) & set(NOIRS))

def _verifie(e, racine):
    q, c, v = e["quarantaine"], e["chemin"], e["sha256"]; float(e["mtime"])
    if not (_garde(q, racine) and _garde(c, racine)):
        return "refus garde interne"
    if not os.path.isfile(q):
        return "skip" if os.path.isfile(c) and _sha256(c) == v else "quarantaine introuvable"
    if _sha256(q) != v:
        return "empreinte quarantaine fausse"
    return "collision a destination" if os.path.isfile(c) and _sha256(c) != v else "ok"

def restaure(manifeste):
    try:
        with open(manifeste, encoding="utf-8") as f:
            entrees = json.load(f)["entrees"]
    except (OSError, ValueError, KeyError, TypeError):
        print("manifeste absent ou invalide : " + manifeste, file=sys.stderr)
        return 2
    racine, refus, ok = os.path.realpath(os.getcwd()) + os.sep, [], []
    for e in entrees:
        try:
            v = _verifie(e, racine)
        except (KeyError, TypeError, ValueError, OSError) as err:
            v = "entree invalide : " + str(err)
        (refus if v not in ("ok", "skip") else ok).append((e, v))
    if refus:
        print("\n".join("refus : %r : %s" % (e, v) for e, v in refus), file=sys.stderr)
        return 3
    for e, v in ok:
        if v == "ok":
            os.makedirs(os.path.dirname(e["chemin"]) or ".", exist_ok=True)
            os.replace(e["quarantaine"], e["chemin"])
            os.utime(e["chemin"], (e["mtime"], e["mtime"]))
    return 0

def mettre_en_quarantaine(plan, garde, racine_q):
    cibles = [c for g in plan["groupes"] for c in g["membres"] if c != g["conserve"]]
    refus = []
    for c in cibles:
        try: garde.verifier(c)
        except RefusChemin as e: refus.append(str(e))
    if refus: print("\n".join(refus), file=sys.stderr); return 3, 0, 0
    dossier = next((os.path.join(racine_q, d) for d in (sorted(os.listdir(racine_q)) if os.path.isdir(racine_q) else []) if os.path.isfile(os.path.join(racine_q, d, "manifeste.json"))), os.path.join(racine_q, time.strftime("%Y-%m-%d")))
    manif = os.path.join(dossier, "manifeste.json")
    data = json.load(open(manif, encoding="utf-8")) if os.path.isfile(manif) else {"version": 1, "date": time.strftime("%Y-%m-%d"), "entrees": []}
    os.makedirs(dossier, exist_ok=True)
    existants, n = {e["chemin"]: e for e in data["entrees"]}, 0
    for c in cibles:
        e = existants.get(c)
        if not os.path.isfile(c):
            if not (e and os.path.isfile(e["quarantaine"]) and _sha256(e["quarantaine"]) == e["sha256"]):
                print("source introuvable : " + c, file=sys.stderr); return 3, 0, 0
            n += 1; continue
        mtime, v = os.stat(c).st_mtime, _sha256(c)
        if not (e and e["sha256"] == v):
            dest = os.path.join(dossier, "f%d.bin" % len(data["entrees"]))
            data["entrees"].append({"chemin": c, "taille": os.path.getsize(c), "sha256": v, "quarantaine": dest, "mtime": mtime})
            json.dump(data, open(manif, "w", encoding="utf-8")); e = data["entrees"][-1]
        os.replace(c, e["quarantaine"]); n += 1
    return 0, n, len(plan["groupes"])

def _mettre(plan_path, rest):
    racine_q, oui = (rest[rest.index("--racine-q") + 1] if "--racine-q" in rest else "quarantaine"), "--oui" in rest
    try:
        with open(plan_path, encoding="utf-8") as f: plan = json.load(f)
        for g in plan["groupes"]:
            if g["empreinte"] is None or g["conserve"] not in g["membres"]: raise ValueError("groupe invalide")
    except (OSError, ValueError, KeyError, TypeError):
        print("plan absent ou invalide : " + plan_path, file=sys.stderr); return 2
    cibles = [c for g in plan["groupes"] for c in g["membres"] if c != g["conserve"]]
    if not oui:
        octets = sum(os.path.getsize(c) for c in cibles if os.path.isfile(c))
        print("groupes=%d fichiers_a_deplacer=%d octets=%d" % (len(plan["groupes"]), len(cibles), octets))
        try: rep = input("o/N : ")
        except EOFError: rep = ""
        if rep != "o": return 3
    rc, deplaces, conserves = mettre_en_quarantaine(plan, Garde([os.getcwd()]), racine_q)
    if rc == 0: print("quarantaine sur le même volume ≠ Go libérés : deplaces=%d conserves=%d" % (deplaces, conserves))
    return rc

if __name__ == "__main__":
    if sys.argv[1:2] == ["mettre"] and len(sys.argv) > 2:
        sys.exit(_mettre(sys.argv[2], sys.argv[3:]))
    if sys.argv[1:2] != ["restaure"]:
        sys.exit("usage : python -m savespace_drive.quarantaine {restaure|mettre} ...")
    sys.exit(restaure(sys.argv[2] if len(sys.argv) > 2 else "quarantaine/manifeste.json"))
