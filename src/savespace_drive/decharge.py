"""savespace_drive.decharge : décharge vérifiée SOURCE -> DEST (DN4B). Autonome, stdlib seule."""
import hashlib, json, os, shutil, sys
from argparse import ArgumentParser; from pathlib import Path
from savespace_drive.chemins import COMPOSANTES_NOIRES, Garde, RefusChemin, dans_le_nuage
def _sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _min_octets(t):
    s = t.strip(); m = {"k": 1024, "m": 1024**2, "g": 1024**3}.get(s[-1:].lower(), 1); v = int(s[:-1] if m != 1 else s)
    if v < 0: raise ValueError(t)
    return v * m
def principal(argv=None):
    a = ArgumentParser(prog="savespace_drive.decharge"); a.add_argument("source", type=Path); a.add_argument("dest", type=Path)
    a.add_argument("--min", default="5M"); a.add_argument("--oui", action="store_true")
    args = a.parse_args(argv)
    try: seuil = _min_octets(args.min)
    except ValueError: print(f"decharge : --min invalide : {args.min}", file=sys.stderr); return 2
    garde = Garde([os.getcwd()])
    try: garde.verifier(args.source); garde.verifier(args.dest)
    except RefusChemin as exc: print(f"decharge : refus — {exc}", file=sys.stderr); return 3
    sr, dr, plan = Path(os.path.realpath(args.source)), Path(os.path.realpath(args.dest)), []
    for d, dn, fn in os.walk(sr):
        dn[:] = sorted(x for x in dn if x not in COMPOSANTES_NOIRES)
        plan += [p for p in (Path(d, n) for n in sorted(fn)) if (st := p.stat()).st_size >= seuil and not dans_le_nuage(st)]
    if not args.oui:
        print(f"fichiers_a_deplacer={len(plan)} octets={sum(p.stat().st_size for p in plan)}")
        try: rep = input("o/N : ")
        except EOFError: rep = ""
        if rep != "o": return 3
    dr.mkdir(parents=True, exist_ok=True); journal, entrees = dr / "deplacements.jsonl", {}
    if journal.is_file():
        with open(journal, encoding="utf-8") as f: entrees = {(e := json.loads(l))["chemin"]: e for l in f if l.strip()}
    for p in plan:
        chemin, empreinte = str(p), _sha256(p); e = entrees.get(chemin)
        if e is not None and e["sha256"] != empreinte:
            print(f"decharge : refus — {chemin} : divergent", file=sys.stderr); return 3
        df = dr / p.relative_to(sr)
        if not (df.is_file() and _sha256(df) == empreinte):
            df.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, df)
            if _sha256(df) != empreinte: print(f"decharge : refus — {chemin} : copie divergente", file=sys.stderr); return 3
        if e is None:
            ligne = json.dumps({"chemin": chemin, "taille": p.stat().st_size, "sha256": empreinte, "quarantaine": str(df), "mtime": p.stat().st_mtime})
            open(journal, "a", encoding="utf-8").write(ligne + "\n"); entrees[chemin] = {"sha256": empreinte}
        os.remove(p)
    print(f"decharge : {len(plan)} fichier(s) traité(s)"); return 0
if __name__ == "__main__": sys.exit(principal())
