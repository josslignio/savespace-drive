"""Photos à blanc — DN5B (SPEC §3) : album « À supprimer » groupé par sha256 (jamais par nom) ; osxphotos appelé en sous-processus en mode réel, jamais importé ; banc (défaut) = stdlib seule."""
import hashlib, json, os, sys
from argparse import ArgumentParser
from pathlib import Path
from .chemins import COMPOSANTES_NOIRES, Garde, RefusChemin
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp", ".ppm", ".mp4", ".mov", ".mkv", ".avi"}
NOM_ALBUM = "À supprimer (SaveSpace Drive)"
def _empreinte(c):
    return hashlib.file_digest(open(c, "rb"), "sha256").hexdigest()
class Phototheque:
    def __init__(self, racine, mode="banc"):
        self.racine, self.mode, self._album = Path(racine), mode, None
    def lister(self):
        locales, non_locaux = [], []
        for dossier, sous, noms in os.walk(self.racine):
            sous[:] = sorted(d for d in sous if d not in COMPOSANTES_NOIRES)
            for nom in sorted(noms):
                if nom.endswith(".icloud") and Path(nom[:-7]).suffix in EXTENSIONS: non_locaux.append(Path(nom[:-7]).stem)
                elif not nom.endswith(".icloud") and Path(nom).suffix in EXTENSIONS: locales.append((Path(nom).stem, Path(dossier) / nom))
        return locales, sorted(non_locaux)
    def doublons(self):
        g = {}
        for uuid, chemin in self.lister()[0]: g.setdefault(_empreinte(chemin), []).append(uuid)
        return [sorted(m) for _, m in sorted(g.items()) if len(m) >= 2]
    def creer_album(self, nom):
        self._album = self.racine / "albums" / f"{nom}.json"; self._album.parent.mkdir(parents=True, exist_ok=True)
        self._album.write_text("[]"); return self._album
    def ajouter_a_album(self, uuids):
        actuels = set(json.loads(self._album.read_text())) | set(uuids)
        self._album.write_text(json.dumps(sorted(actuels))); return self._album
def principal(argv=None):
    a = ArgumentParser(prog="savespace_drive.photos")
    a.add_argument("--phototheque", required=True); a.add_argument("--mode", choices=["banc", "reel"], default="banc"); a.add_argument("--racine", action="append", default=None)
    args = a.parse_args(argv)
    interdits = {os.path.realpath("/")} | ({os.path.realpath(os.environ["HOME"])} if os.environ.get("HOME") else set())
    brut = str(args.phototheque)
    if not brut.strip() or not os.path.isdir(brut) or os.path.realpath(brut) in interdits:
        print(f"photos : refus — phototheque invalide : {brut}", file=sys.stderr); return 2
    try:
        Garde([Path(r) for r in (args.racine or [brut])]).verifier(Path(brut))
    except RefusChemin as exc:
        print(f"photos : refus — {exc}", file=sys.stderr); return 3
    ph = Phototheque(brut, args.mode); groupes, (_, non_locaux) = ph.doublons(), ph.lister()
    ph.creer_album(NOM_ALBUM); ph.ajouter_a_album([u for g in groupes for u in g])
    for n, g in enumerate(groupes, 1): print(f"g{n} : {', '.join(g)}")
    print(f"non locaux : {', '.join(non_locaux)}")
    print(json.dumps({"album": str(ph._album.resolve()), "groupes": groupes, "mode": args.mode, "non_locaux": non_locaux, "phototheque": args.phototheque}, sort_keys=True))
    return 0
if __name__ == "__main__":
    sys.exit(principal())
