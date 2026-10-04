"""APP2 (fenêtre de bureau + nouvel écran) — hermétique : dossiers synthétiques sous tmp_path, HOME jetable, sans fenêtre."""
import json, socket, sys, threading, time, urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from savespace_drive import app, bureau, cli  # noqa: E402
from test_app import DIRECT, _jeu, _photo, _post, ecran, maison  # noqa: E402,F401  (fixtures partagées)


def test_analyse_structuree_pour_les_cartes(ecran, tmp_path):
    s, _ = ecran
    racine = _jeu(tmp_path / "jeu")
    (racine / "Library/Caches").mkdir(parents=True)
    (racine / "Library/Caches/c.db").write_bytes(b"C" * 1200)
    r = _post(s, "analyser", racine)["resultat"]
    assert (r["recuperables"], r["recuperables_octets"], r["groupes"]) == ("6,5 Ko", 6500, 2)
    assert r["doublons"][0] == {"taille": "3,0 Ko", "garde": "a/photo.jpg", "en_trop": ["b/photo (1).jpg", "a/Copie de photo.jpg"]}
    assert r["doublons"][1]["en_trop"] == ["z/doc.pdf"], "groupes triés par place récupérable décroissante"
    assert (r["caches"], r["caches_taille"], r["proteges"]) == (1, "1,2 Ko", 1)
    assert r["gros"][0] == ["a/Copie de photo.jpg", "3,0 Ko"] and not any(".ssh" in c for g in r["doublons"] for c in g["en_trop"])


def test_apercu_structure_pour_la_confirmation(ecran, tmp_path):
    s, _ = ecran
    racine = _jeu(tmp_path / "jeu")
    avant = _photo(racine)
    d = _post(s, "preparer", racine)
    assert (d["confirmer"], d["nombre"], d["taille"], d["groupes"], d["quarantaine"]) == (True, 3, "6,5 Ko", 2, "quarantaine")
    assert sorted(c for g in d["plan"] for c in g["en_trop"]) == ["a/Copie de photo.jpg", "b/photo (1).jpg", "z/doc.pdf"]
    assert _photo(racine) == avant, "l'aperçu ne doit rien bouger"


def test_action_longue_repond_en_cours_puis_suivre(ecran, tmp_path, monkeypatch):
    s, _ = ecran
    racine, feu = _jeu(tmp_path / "jeu"), threading.Event()
    vrai = app.analyse.analyser
    monkeypatch.setattr(app, "ATTENTE", 0.05)
    monkeypatch.setattr(app.analyse, "analyser", lambda *a: (feu.wait(10), vrai(*a))[1])
    assert _post(s, "analyser", racine) == {"en_cours": True}
    assert _post(s, "suivre") == {"en_cours": True}
    autre = _post(s, "preparer", racine)
    assert autre.get("erreur") and "déjà en cours" in autre["texte"], "deux actions en même temps"
    feu.set()
    for _ in range(100):
        if not (d := _post(s, "suivre")).get("en_cours"):
            break
        time.sleep(0.05)
    assert d["resultat"]["recuperables"] == "6,5 Ko"


def test_quitter_marche_meme_pendant_une_action(ecran, tmp_path, monkeypatch):
    s, _ = ecran
    feu = threading.Event()
    monkeypatch.setattr(app, "ATTENTE", 0.05)
    monkeypatch.setattr(app.analyse, "analyser", lambda *a: feu.wait(10))
    assert _post(s, "analyser", _jeu(tmp_path / "jeu")) == {"en_cours": True}
    assert "fermé" in _post(s, "quitter")["texte"] and s.fini
    feu.set()


def test_page_autonome_sans_internet_ni_innerhtml(ecran):
    s, url = ecran
    page = DIRECT.open(url, timeout=10).read().decode()
    assert "http://" not in page and "https://" not in page and "//cdn" not in page, "ressource chargée depuis Internet"
    assert "innerHTML" not in page, "les noms de fichiers doivent passer par textContent"
    assert "prefers-color-scheme:dark" in page and "-apple-system" in page and "Segoe UI" in page
    for mot in ("Analyser", "Annuler / restaurer", "Oui, ranger", "Doublons", "Gros fichiers", "Caches et journaux"):
        assert mot in page, mot


@pytest.mark.parametrize("plateforme, videos, osxphotos", [("darwin", "Movies", True), ("win32", "Videos", False)])
def test_differences_mac_windows(maison, monkeypatch, plateforme, videos, osxphotos):
    (maison / "Movies").mkdir()
    (maison / "Videos").mkdir()
    monkeypatch.setattr(sys, "platform", plateforme)
    monkeypatch.setattr(app.drives, "rclone", lambda: None)  # shutil.which ne sait pas faire semblant d'être sous Windows
    monkeypatch.setattr(app.doctor, "examiner", lambda: {"outils": {n: {"present": True} for n in ("czkawka_cli", "osxphotos", "rclone")}})
    assert dict(app.raccourcis())["Vidéos"] == str(maison / videos)
    assert ("osxphotos" in dict(app.outils())) is osxphotos and "rclone" in dict(app.outils())
    assert ("osxphotos" in app.page("j")) is osxphotos


def test_sans_outil_externe_la_page_marche(maison, monkeypatch):
    monkeypatch.setattr(app.doctor, "examiner", lambda: {"outils": {n: {"present": False} for n in ("czkawka_cli", "osxphotos", "rclone")}})
    page = app.page("j")
    assert "Outils en plus" not in page and "Analyser" in page


def test_serveur_sans_resolution_de_nom(monkeypatch):
    def interdit(*a):
        raise AssertionError("résolution de nom au lancement (35 s mesurées dans l'app Mac)")
    monkeypatch.setattr(socket, "getfqdn", interdit)
    monkeypatch.setattr(socket, "gethostbyaddr", interdit)
    s, url = app.creer_serveur()
    s.server_close()
    assert url.startswith("http://127.0.0.1:") and s.server_name == "127.0.0.1"


class FausseFenetre:
    def __init__(self, choix=None):
        self.choix, self.detruite = choix, False

    def destroy(self):
        self.detruite = True

    def create_file_dialog(self, genre):
        return self.choix


def test_fenetre_part_avec_le_serveur():
    s, _ = app.creer_serveur()
    f = FausseFenetre()
    fil = threading.Thread(target=bureau.servir, args=(s, f), daemon=True)
    fil.start()
    time.sleep(0.2)
    assert fil.is_alive() and not f.detruite
    s.fini = True
    fil.join(5)
    s.server_close()
    assert f.detruite and not fil.is_alive()


def test_selecteur_de_dossier(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", type(sys)("webview"))
    sys.modules["webview"].FileDialog = type("FileDialog", (), {"FOLDER": 20})
    api = bureau.Api()
    api.fenetre = FausseFenetre(("/un/dossier",))
    assert api.choisir() == "/un/dossier"
    api.fenetre = FausseFenetre(None)
    assert api.choisir() == ""


def test_sans_pywebview_repli_sur_le_navigateur(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview -> ImportError
    monkeypatch.setattr(app, "principal", lambda argv=None: 42)
    assert bureau.principal([]) == 42
    monkeypatch.setattr(bureau, "principal", lambda argv=None: 7)
    assert cli.main(["bureau"]) == 7


# ---- Le fichier gardé est l'original, jamais la copie (un test par motif) ---------------------------------
@pytest.mark.parametrize("original, copie", [  # l'original est plus profond, au nom plus long et après dans l'alphabet :
    ("z/Vacances Bretagne.mp4", "Copie de V.mp4"), ("z/Vacances Bretagne.mp4", "V - copie.mp4"),  # seul le motif le sauve
    ("z/Vacances Bretagne.mp4", "Copy of V.mp4"), ("z/Vacances Bretagne.mp4", "V copy.mp4"),
    ("z/Facture électricité.pdf", "F (1).pdf"), ("z/Facture électricité.pdf", "F (2).pdf"),
    ("z/Facture électricité.pdf", "F_1.pdf"), ("z/Facture électricité.pdf", "F 1.pdf"),
])
def test_on_garde_l_original_pas_la_copie(original, copie):
    for ordre in ([original, copie], [copie, original]):
        assert app._original_d_abord(ordre)[0] == original, (ordre, "la copie a été gardée")


@pytest.mark.parametrize("gagnant, perdant, regle", [
    ("Vacances Bretagne.mp4", "a/V.mp4", "le moins profond"),
    ("IMG_2041.HEIC", "Téléphone/IMG_2041.HEIC", "IMG_2041 n'est pas une copie"),
    ("rapport.pdf", "rapport-final.pdf", "le nom le plus court"),
    ("a.pdf", "b.pdf", "l'ordre alphabétique"),
    ("z/Copyright.pdf", "Copie de Copyright.pdf", "Copyright n'est pas une copie"),
])
def test_departage_des_originaux(gagnant, perdant, regle):
    for ordre in ([gagnant, perdant], [perdant, gagnant]):
        assert app._original_d_abord(ordre)[0] == gagnant, regle


def test_l_ecran_range_la_copie_et_garde_l_original(ecran, tmp_path):
    s, _ = ecran
    racine = tmp_path / "jeu"
    for rel in ("Copie de Vacances.mp4", "Vacances (1).mp4", "Vacances.mp4"):
        (racine / rel).parent.mkdir(parents=True, exist_ok=True)
        (racine / rel).write_bytes(b"V" * 2000)
    assert _post(s, "analyser", racine)["resultat"]["doublons"][0]["garde"] == "Vacances.mp4"
    d = _post(s, "preparer", racine)
    assert d["plan"] == [{"garde": "Vacances.mp4", "en_trop": ["Vacances (1).mp4", "Copie de Vacances.mp4"]}]
    assert "3 fichiers" not in d["texte"] and "on garde : Vacances.mp4" in d["texte"]
    assert not _post(s, "ranger", racine).get("erreur")
    assert sorted(p.name for p in racine.iterdir() if p.is_file()) == ["Vacances.mp4"], "l'original doit rester à sa place"


def test_la_fenetre_fermee_le_processus_sort_sans_attendre(monkeypatch):
    faux = type(sys)("webview")
    fenetre = type("F", (), {"events": type("E", (), {"closed": None})()})()

    class Evenement:
        def __iadd__(self, f):
            return self
    fenetre.events.closed = Evenement()
    faux.create_window = lambda *a, **k: fenetre
    feu = threading.Event()
    faux.start = lambda **k: threading.Thread(target=feu.wait).start()  # un fil non daemon, bloqué (libéré en fin de test)
    sorties = []
    monkeypatch.setitem(sys.modules, "webview", faux)
    monkeypatch.setattr(bureau, "servir", lambda s, f: None)
    monkeypatch.setattr(bureau.os, "_exit", lambda code: sorties.append(code))
    try:
        bureau.principal([])
    finally:
        feu.set()
    assert sorties == [0], "le processus attendrait un fil bloqué de pywebview"
