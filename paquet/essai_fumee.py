"""Essai de fumée de l'app CONSTRUITE (Mac) : lancer, vérifier fenêtre + écran, quitter proprement, aucun reste.
Usage : python paquet/essai_fumee.py "dist/SaveSpace Drive.app" [--analyser DOSSIER]
--analyser ne fait qu'une ANALYSE (lecture seule) ; rien n'est rangé ni déplacé. Seuls des chiffres sont imprimés."""
import json, subprocess, sys, time, urllib.request
from pathlib import Path

import Quartz

APP = Path(sys.argv[1]).resolve()
EXE = APP / "Contents" / "MacOS" / APP.stem
DOSSIER = sys.argv[sys.argv.index("--analyser") + 1] if "--analyser" in sys.argv else None
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fenetres(pid):
    return [w for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
            if w["kCGWindowOwnerPID"] == pid and w["kCGWindowLayer"] == 0]


def post(base, jeton, action, corps):
    req = urllib.request.Request(f"{base}/{action}", json.dumps(corps).encode(), {"X-Jeton": jeton})
    with DIRECT.open(req, timeout=60) as r:
        return json.loads(r.read())


def principal():
    t0 = time.time()
    p = subprocess.Popen([str(EXE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ligne = p.stdout.readline().strip()  # « SaveSpace Drive : http://127.0.0.1:PORT/?t=JETON »
    assert ligne.startswith("SaveSpace Drive : http://127.0.0.1:"), f"pas d'adresse : {ligne!r} {p.stderr.read()}"
    url = ligne.split(" : ", 1)[1]
    base, jeton = url.split("/?t=")
    page = DIRECT.open(url, timeout=30).read().decode()
    assert "SaveSpace Drive" in page and "Annuler / restaurer" in page, "page incomplète"
    print(f"écran : HTTP 200, {len(page)} octets, {time.time() - t0:.1f} s après le lancement")
    fin = time.time() + 30
    while not fenetres(p.pid) and time.time() < fin:
        time.sleep(0.3)
    f = fenetres(p.pid)
    assert f, "aucune fenêtre à l'écran"
    b = f[0]["kCGWindowBounds"]
    print(f"fenêtre : {len(f)} à l'écran, {int(b['Width'])}×{int(b['Height'])} points, {time.time() - t0:.1f} s après le lancement")
    if DOSSIER:
        t1, d = time.time(), post(base, jeton, "analyser", {"dossier": DOSSIER})
        while d.get("en_cours"):
            time.sleep(1)
            d = post(base, jeton, "suivre", {})
        assert not d.get("erreur"), d["texte"]
        r = d["resultat"]
        print(f"analyse (lecture seule) : {time.time() - t1:.1f} s ; total {r['total']} ; récupérable {r['recuperables']} ; "
              f"{r['groupes']} groupes de doublons ; {len(r['gros'])} gros fichiers ; {r['caches']} caches")
    post(base, jeton, "quitter", {})
    rc = p.wait(timeout=20)
    time.sleep(1)
    restes = subprocess.run(["pgrep", "-f", str(EXE)], capture_output=True, text=True).stdout.split()
    print(f"quitter : code de sortie {rc}, processus restants : {len(restes)}, fenêtres restantes : {len(fenetres(p.pid))}")
    assert rc == 0 and not restes, "sortie sale"
    print("ESSAI DE FUMÉE : OK")


if __name__ == "__main__":
    principal()
