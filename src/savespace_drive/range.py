"""savespace_drive.range : rangement de CIBLE en <= N dossiers (SPEC S1, DN6C). Stdlib seule."""
import hashlib, json, os, subprocess, sys, time
from savespace_drive.chemins import Garde, RefusChemin
EXT = {e: c for c, l in {"Documents": ".pdf .txt .md .doc .docx .rtf .json", "Images": ".jpg .jpeg .png .gif .heic .bmp .svg .ppm", "Vidéos": ".mp4 .mov .mkv .avi", "Musique": ".mp3 .m4a .wav", "Archives": ".zip .tar .gz .rar .7z .dmg"}.items() for e in l.split()}
def _cat(nom, autorises):
    c = EXT.get(os.path.splitext(nom)[1].lower()); return c if c in autorises else "Divers"
def _distant(cible, autorises, oui):
    try: ok = subprocess.run(["rclone", "lsjson", cible], capture_output=True, text=True, timeout=30).returncode == 0
    except OSError: ok = False
    if not ok: print("range : rclone indisponible ou en echec", file=sys.stderr); return 3
    print("range : remote hors de portee de cette version", file=sys.stderr); return 3
def principal(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pos = [a for a in argv if not a.startswith("-")]
    try: n = int(argv[argv.index("--max-dossiers") + 1]) if "--max-dossiers" in argv else 10
    except (ValueError, IndexError): n = -1
    if not pos or not (2 <= n <= 50): print("range : usage ou --max-dossiers hors [2,50]", file=sys.stderr); return 2
    cible, oui, autorises = pos[0], "--oui" in argv, set(["Documents", "Images", "Vidéos", "Musique", "Archives"][: n - 1])
    if ":" in cible: return _distant(cible, autorises, oui)
    if not os.path.isdir(cible) or os.path.realpath(cible) == "/" or (os.environ.get("HOME") and os.path.realpath(cible) == os.path.realpath(os.environ["HOME"])): print("range : cible locale invalide", file=sys.stderr); return 2
    garde, occupes, plan, dossiers, octets = Garde([cible]), set(os.listdir(cible)), [], set(), 0
    fichiers = sorted(f for f in os.listdir(cible) if os.path.isfile(os.path.join(cible, f)) and not os.path.islink(os.path.join(cible, f)))
    for nom in fichiers:
        src, cat, dst = os.path.join(cible, nom), _cat(nom, autorises), os.path.join(cible, _cat(nom, autorises), nom)
        if (cat in occupes and not os.path.isdir(os.path.join(cible, cat))) or os.path.exists(dst): print("range : collision pour " + nom, file=sys.stderr); return 3
        try: garde.verifier(src); garde.verifier(dst)
        except RefusChemin as e: print("range : refus — %s" % e, file=sys.stderr); return 3
        plan.append((src, dst, cat)); dossiers.add(cat); octets += os.path.getsize(src)
    if oui and plan:
        os.makedirs("rangement", exist_ok=True); data = {"version": 1, "date": time.strftime("%Y-%m-%d"), "entrees": []}
        for src, dst, cat in plan:
            os.makedirs(os.path.join(cible, cat), exist_ok=True); sha = hashlib.sha256(open(src, "rb").read()).hexdigest()
            data["entrees"].append({"chemin": os.path.realpath(src), "taille": os.path.getsize(src), "sha256": sha, "quarantaine": os.path.realpath(dst), "mtime": os.stat(src).st_mtime})
            json.dump(data, open(os.path.join("rangement", "manifeste.json"), "w", encoding="utf-8")); os.replace(src, dst)
    for src, dst, *_r in plan: print(src + " -> " + dst)
    print("o/N : ")
    print(json.dumps({"deplacements": len(plan), "dossiers": sorted(dossiers), "octets": octets}, sort_keys=True))
    return 0
if __name__ == "__main__": sys.exit(principal())
