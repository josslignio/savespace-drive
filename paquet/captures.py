"""Captures d'écran de la fenêtre (outil de développement, Mac seulement, jamais livré dans l'app).
Tout se passe dans une MAISON DE DÉMO synthétique (HOME remplacé) : aucun fichier réel n'est lu ni déplacé.
Usage : python paquet/captures.py DOSSIER_DEMO DOSSIER_CAPTURES"""
import os, subprocess, sys, time
from pathlib import Path

DEMO, SORTIE = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
FICHIERS = {  # chemin : (graine, Mo) — même graine = mêmes octets = doublon
    "Downloads/Vacances Bretagne 2025.mp4": (1, 64), "Downloads/Vacances Bretagne 2025 (1).mp4": (1, 64),
    "Downloads/Copie de Vacances Bretagne 2025.mp4": (1, 64), "Downloads/photos-anniversaire.zip": (2, 31),
    "Downloads/Envoi/photos-anniversaire.zip": (2, 31), "Downloads/Facture électricité mars.pdf": (3, 0.4),
    "Downloads/Facture électricité mars (1).pdf": (3, 0.4), "Downloads/Téléphone/IMG_2041.HEIC": (4, 2.4),
    "Downloads/IMG_2041.HEIC": (4, 2.4), "Downloads/Installer Zoom.pkg": (5, 48), "Downloads/Rapport annuel.pdf": (6, 3.1),
    "Downloads/Ancien Mac/Library/Caches/com.apple.Safari/Cache.db": (7, 9), "Downloads/Ancien Mac/Library/Logs/install.log": (8, 1.2),
    "Downloads/Musique/Concert.m4a": (9, 18), "Desktop/notes.txt": (10, 0.01), "Documents/CV.pdf": (11, 0.2), "Movies/film.mov": (12, 5),
}


def demo():
    for rel, (graine, mo) in FICHIERS.items():
        p = DEMO / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            bloc = (bytes([graine]) * 64) * 16384  # 1 Mio déterministe par graine
            octets = int(mo * 1_000_000)
            p.write_bytes((bloc * (octets // len(bloc) + 1))[:octets])


demo()
os.environ["HOME"] = str(DEMO)  # avant tout import : Path.home() pointe sur la maison de démo
SORTIE.mkdir(parents=True, exist_ok=True)
import Quartz, webview  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402
from savespace_drive import bureau, app  # noqa: E402


def fenetre_id():
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID):
        if w["kCGWindowOwnerPID"] == os.getpid() and w["kCGWindowLayer"] == 0:
            return w["kCGWindowNumber"]


def attendre(f, js, delai=60):
    fin = time.time() + delai
    while time.time() < fin:
        if f.evaluate_js(js):
            return
        time.sleep(0.2)
    raise SystemExit(f"état jamais atteint : {js}")


def photo(nom):
    """La fenêtre entière (barre de titre comprise), capturée par le processus lui-même : sa propre fenêtre."""
    time.sleep(0.8)
    image = Quartz.CGWindowListCreateImage(Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow, fenetre_id(),
                                           Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageBestResolution)
    if image is None:  # sans l'autorisation « Enregistrement de l'écran », on retombe sur screencapture
        return subprocess.run(["screencapture", "-x", f"-l{fenetre_id()}", str(SORTIE / nom)], check=True)
    url = Quartz.CFURLCreateWithFileSystemPath(None, str(SORTIE / nom), Quartz.kCFURLPOSIXPathStyle, False)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, image, None)
    assert Quartz.CGImageDestinationFinalize(dest), nom
    print("capture :", SORTIE / nom, Quartz.CGImageGetWidth(image), "x", Quartz.CGImageGetHeight(image), flush=True)


def apparence(nom):
    from AppKit import NSApp, NSAppearance
    AppHelper.callAfter(lambda: NSApp.setAppearance_(NSAppearance.appearanceNamed_(nom)))
    time.sleep(1)


def pilote(f, s):
    try:
        attendre(f, "typeof analyser==='function' && !!dossier")
        for theme, suffixe in (("NSAppearanceNameAqua", ""), ("NSAppearanceNameDarkAqua", "_sombre")):
            apparence(theme)
            f.evaluate_js("choisir(document.querySelector('.puce[data-c]').dataset.c)")
            photo(f"1_accueil{suffixe}.png")
            f.evaluate_js("travail('Analyse de « '+nom+' »…')")
            photo(f"2_analyse_en_cours{suffixe}.png")
            f.evaluate_js("analyser()")
            attendre(f, "!document.getElementById('cartes').hidden")
            f.evaluate_js("document.querySelector('#c-doublons details').open=true")
            photo(f"3_resultat{suffixe}.png")
            f.evaluate_js("preparer()")
            attendre(f, "!document.getElementById('voile').hidden")
            photo(f"4_confirmation{suffixe}.png")
            f.evaluate_js("document.getElementById('f-oui').click()")
            attendre(f, "document.getElementById('titre').textContent==\"C'est fait\"")
            photo(f"5_rangement_fait{suffixe}.png")
            f.evaluate_js("document.getElementById('restaurer').click()")
            attendre(f, "document.getElementById('titre').textContent=='Tout est revenu'")
    finally:
        s.fini = True


s, url = app.creer_serveur()
f = webview.create_window("SaveSpace Drive", url, js_api=bureau.Api(), width=1040, height=780)
f.events.closed += lambda: setattr(s, "fini", True)
import threading  # noqa: E402
threading.Thread(target=bureau.servir, args=(s, f), daemon=True).start()
webview.start(pilote, (f, s), localization=bureau.FRANCAIS)
s.server_close()
