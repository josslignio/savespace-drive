"""Corbeille caches/logs/téléchargements/installeurs -> <HOME>/.Trash (DN3B, SPEC §1). Rename seul, stdlib."""
import hashlib, json, os, sys, time
from argparse import ArgumentParser
from pathlib import Path
from savespace_drive.chemins import Garde, RefusChemin, dans_le_nuage
NOIRES = {".ssh", ".gnupg", ".git", "Keychains"}
def _sha256(p):
    with open(p, "rb") as f: return hashlib.sha256(f.read()).hexdigest()
def cibles(racine, jours):
    limite, vus = time.time() - jours * 86400, []
    for d, sous, noms in os.walk(racine):
        sous[:] = [s for s in sous if s not in NOIRES]
        rel = Path(d).relative_to(racine).parts
        c, dl = rel[:2] in (("Library", "Caches"), ("Library", "Logs")), rel[:1] == ("Downloads",)
        for n in noms:
            p = Path(d) / n
            if dans_le_nuage(st := p.stat()): continue  # pas sur ce disque : rien à libérer, et le lire le téléchargerait
            if c or Path(n).suffix.lower() in (".dmg", ".pkg") or (dl and st.st_mtime < limite): vus.append(p)
    return sorted(set(vus))
def principal(argv=None):
    a = ArgumentParser(prog="savespace_drive.caches")
    a.add_argument("--racine", type=Path, default=Path(".")); a.add_argument("--jours", type=int, default=30); a.add_argument("--oui", action="store_true"); args = a.parse_args(argv)
    home = os.environ.get("HOME"); interdits = {os.path.realpath("/")} | ({os.path.realpath(home)} if home else set()); racine = Path(os.path.realpath(args.racine))
    if str(racine) in interdits: print("caches : refus — racine interdite : " + str(args.racine), file=sys.stderr); return 2
    c = cibles(racine, args.jours)
    if not args.oui:
        print("cibles=%d octets=%d" % (len(c), sum(p.stat().st_size for p in c)))
        try: rep = input("o/N : ")
        except EOFError: rep = ""
        if rep != "o": return 3
    try: [Garde([racine]).verifier(p) for p in c]
    except RefusChemin as exc: print("caches : refus — " + str(exc), file=sys.stderr); return 3
    corbeille = os.path.join(home, ".Trash"); os.makedirs(corbeille, exist_ok=True); manif = os.path.join(corbeille, "manifeste.json")
    data, n = {"version": 1, "date": time.strftime("%Y-%m-%d"), "entrees": []}, 0
    for i, p in enumerate(c):
        e = {"chemin": p.relative_to(racine).as_posix(), "taille": p.stat().st_size, "sha256": _sha256(p), "quarantaine": os.path.join(corbeille, "c%d.bin" % i), "mtime": p.stat().st_mtime}; data["entrees"].append(e)
        with open(manif, "w", encoding="utf-8") as f: json.dump(data, f); os.replace(p, e["quarantaine"]); n += 1
    print("deplaces=%d : corbeille même volume ≠ Go libérés ; sur volume synchronisé iCloud, la suppression se propage" % n)
    return 0
if __name__ == "__main__":
    sys.exit(principal())
