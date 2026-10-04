"""Drives : iCloud Drive (dossier local, fichiers pas téléchargés jamais ouverts) et Google Drive / OneDrive / Dropbox
(rclone). Hermétique : HOME jetable, faux rclone (tests/faux_rclone.py) ou vrai rclone sur un remote alias LOCAL
(remote_local.py). Aucun vrai compte n'est jamais touché."""
import builtins, io, json, os, shutil, stat, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from savespace_drive import analyse, app, doublons, drives, remote_local  # noqa: E402
from savespace_drive.chemins import Garde, RefusChemin, SF_DATALESS  # noqa: E402
from test_app import DIRECT, _photo, ecran, maison  # noqa: E402,F401
import urllib.request  # noqa: E402

FAUX = Path(__file__).with_name("faux_rclone.py")
JETON = "JETON-SECRET-ne-doit-jamais-sortir"


def _post(s, action, **corps):
    req = urllib.request.Request(f"http://127.0.0.1:{s.server_port}/{action}", json.dumps(corps).encode(),
                                 {"X-Jeton": s.jeton, "Host": s.hote})
    with DIRECT.open(req, timeout=30) as r:
        return json.loads(r.read())


# ---- iCloud Drive : un fichier pas téléchargé n'est JAMAIS ouvert ----------------------------------------------
class Stat:  # le vrai stat, avec le drapeau « pas téléchargé » que pose macOS (ou l'attribut Windows)
    def __init__(self, st, **drapeaux):
        self.__dict__.update(drapeaux, _st=st)

    def __getattr__(self, k):
        return getattr(self._st, k)


@pytest.fixture
def icloud(maison, monkeypatch):
    d = maison / "Library/Mobile Documents/com~apple~CloudDocs"
    for rel, octets in {"Photos/plage.jpg": b"P" * 4000, "Photos/Copie de plage.jpg": b"P" * 4000, "doc.pdf": b"D" * 900,
                        "nuage/plage.jpg": b"P" * 4000, "nuage/doc.pdf": b"D" * 900}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(octets)
    monkeypatch.setattr(sys, "platform", "darwin")
    return d


def _nuage(monkeypatch, dossier, noms, **drapeaux):
    """Les fichiers dont le nom est dans `noms` se disent « pas téléchargés » ; toute ouverture de l'un d'eux est notée."""
    vrai_stat, vrai_open, ouverts = os.stat, builtins.open, []
    cibles = {os.path.realpath(dossier / n) for n in noms}

    def faux_stat(p, *a, **k):
        st = vrai_stat(p, *a, **k)
        return Stat(st, **drapeaux) if os.path.realpath(p) in cibles else st

    def faux_open(p, *a, **k):
        if isinstance(p, (str, os.PathLike)) and os.path.realpath(p) in cibles:
            ouverts.append(os.fspath(p))
        return vrai_open(p, *a, **k)
    monkeypatch.setattr(os, "stat", faux_stat)
    monkeypatch.setattr(builtins, "open", faux_open)
    monkeypatch.setattr(io, "open", faux_open)
    return ouverts


@pytest.mark.parametrize("drapeaux", [{"st_flags": SF_DATALESS}, {"st_file_attributes": 0x400000}], ids=["mac", "windows"])
def test_fichiers_pas_telecharges_jamais_ouverts(icloud, monkeypatch, drapeaux):
    ouverts = _nuage(monkeypatch, icloud, ["nuage/plage.jpg", "nuage/doc.pdf"], **drapeaux)
    r = app.analyser(Path(app.dossier_valide(str(icloud))))["resultat"]
    _, apercu = app.preparer(Path(os.path.realpath(icloud)))
    g = doublons.detecter(icloud, Garde([icloud]))
    assert ouverts == [], f"fichiers pas téléchargés ouverts (donc téléchargés) : {ouverts}"
    assert r["nuage"].startswith("2 fichiers (4,9 Ko) sont seulement dans iCloud"), r["nuage"]
    assert r["groupes"] == 1 and r["doublons"][0]["en_trop"] == ["Photos/Copie de plage.jpg"]
    assert not any("nuage/" in c for x in apercu["plan"] for c in [x["garde"], *x["en_trop"]])
    assert not any("nuage/" in c for x in g for c in x["membres"])
    assert "rien n'a été téléchargé" in app.analyser(Path(os.path.realpath(icloud)))["texte"]


def test_renvoye_au_nuage_entre_apercu_et_rangement(icloud, monkeypatch):
    dossier = Path(os.path.realpath(icloud))
    plan, _ = app.preparer(dossier)
    avant = _photo(dossier)
    ouverts = _nuage(monkeypatch, dossier, ["Photos/Copie de plage.jpg"], st_flags=SF_DATALESS)
    with pytest.raises(app.Refus, match="plus téléchargé"):
        app.ranger(dossier, plan)
    assert ouverts == [] and _photo(dossier) == avant


def test_icloud_dans_la_page_et_aller_retour(icloud, ecran):
    s, url = ecran
    page = DIRECT.open(url, timeout=10).read().decode()
    assert "Où chercher ?" in page and "iCloud Drive" in page and "Google Drive" in page and "OneDrive" in page and "Dropbox" in page
    assert "retire aussi de tous tes appareils" in page and "quarantaine" in page
    avant = _photo(icloud)
    assert _post(s, "preparer", dossier=str(icloud))["nombre"] == 3
    assert not _post(s, "ranger", dossier=str(icloud)).get("erreur")
    assert not (icloud / "Photos/Copie de plage.jpg").exists()
    assert not _post(s, "restaurer", dossier=str(icloud)).get("erreur") and _photo(icloud) == avant


def test_icloud_seul_coin_de_library_ouvert(icloud, maison):
    Garde([icloud]).verifier(icloud / "doc.pdf")
    for interdit in (maison / "Library/Caches/x", maison / "Library/Mobile Documents/iCloud~com~app/x"):
        with pytest.raises(RefusChemin):
            Garde([maison]).verifier(interdit)


def test_sans_icloud_pas_de_choix_icloud(maison, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert app.icloud() is None and 'data-l="icloud"' not in app.page("j")


# ---- Google Drive / OneDrive / Dropbox par un faux rclone ------------------------------------------------------
@pytest.fixture
def faux(maison, tmp_path, monkeypatch):
    d = tmp_path / "faux"
    d.mkdir()
    shutil.copy(FAUX, d / "faux_rclone.py")
    if os.name == "nt":
        exe = d / "rclone.cmd"
        exe.write_text(f'@"{sys.executable}" "{d / "faux_rclone.py"}" %*\n')
    else:
        exe = d / "rclone"
        exe.write_text(f"#!{sys.executable}\n" + FAUX.read_text())
        exe.chmod(0o755)
    monkeypatch.setattr(drives, "rclone", lambda: str(exe))
    etat = d / "rclone.json"

    def poser(cle="gdrive", type_="drive", **e):
        drives.conf().parent.mkdir(parents=True, exist_ok=True)
        drives.conf().write_text(f"[{cle}]\ntype = {type_}\n")
        etat.write_text(json.dumps(e))
    poser.lire = lambda: json.loads(etat.read_text())
    poser.ecrire = lambda e: etat.write_text(json.dumps(e))
    return poser


FICHIERS = [{"p": "Vacances.mp4", "t": 5_000_000, "h": "aa"}, {"p": "Envoi/Copie de Vacances.mp4", "t": 5_000_000, "h": "aa"},
            {"p": "Vacances (1).mp4", "t": 5_000_000, "h": "aa"}, {"p": "Factures/mars.pdf", "t": 300_000, "h": "bb"},
            {"p": "mars.pdf", "t": 300_000, "h": "bb"}, {"p": "Notes", "t": -1}, {"p": "Notes 2", "t": -1},  # Google Docs
            {"p": "deux.txt", "t": 70, "h": "cc"}, {"p": "deux (1).txt", "t": 70, "h": "zz"},  # même nom deux fois,
            {"p": "deux (1).txt", "t": 70, "h": "cc"},  # contenus différents : la corbeille par chemin prendrait les deux
            {"p": "Autre film.mp4", "t": 5_000_000, "h": "ee"},  # même taille, autre contenu : pas un doublon
            {"p": "seul.zip", "t": 9_000_000, "h": "dd"}]
ESPACE = {"total": 15_000_000_000, "used": 9_000_000_000, "trashed": 1_200_000_000, "other": 4_000_000_000, "free": 2e9}


def _commandes(appels):
    return [a["argv"][0] if a["argv"][0] != "config" else "config create" for a in appels]


def test_doublons_par_empreinte_sans_rien_telecharger(faux, ecran):
    s, _ = ecran
    faux(fichiers=FICHIERS, about=ESPACE)
    r = _post(s, "analyser", drive="gdrive")["resultat"]
    assert (r["groupes"], r["recuperables"], r["espace"]) == (2, "10,3 Mo", "Espace utilisé : 13,0 Go sur 15,0 Go")
    assert r["doublons"][0] == {"taille": "5,0 Mo", "garde": "Vacances.mp4", "en_trop": ["Vacances (1).mp4", "Envoi/Copie de Vacances.mp4"]}
    assert (r["corbeille"], r["autres"]) == ("1,2 Go", "4,0 Go") and r["gros"][0] == ["seul.zip", "9,0 Mo"]
    appels = faux.lire()["appels"]
    assert set(_commandes(appels)) == {"lsjson", "about"}, "seules la liste et l'espace sont lus : rien n'est téléchargé"
    assert all(a["argv"][a["argv"].index("--hash-type") + 1] == "md5" for a in appels if a["argv"][0] == "lsjson")


def test_rien_ne_part_sans_le_oui(faux, ecran):
    s, _ = ecran
    faux(fichiers=FICHIERS, about=ESPACE)
    assert _post(s, "ranger", drive="gdrive").get("erreur"), "corbeille sans aperçu"
    _post(s, "analyser", drive="gdrive")
    d = _post(s, "preparer", drive="gdrive")
    assert (d["confirmer"], d["nombre"], d["drive"]) == (True, 3, "Google Drive")
    assert "→ corbeille : Factures/mars.pdf" in d["texte"] and "deux.txt" not in d["texte"] and "Notes" not in d["texte"] and "deux (1).txt" not in d["texte"]
    assert "Autre film" not in d["texte"]
    assert "delete" not in _commandes(faux.lire()["appels"]), "l'aperçu a supprimé quelque chose"
    fait = _post(s, "ranger", drive="gdrive")
    assert fait.get("fait") and "3 fichiers mis dans la corbeille de Google Drive" in fait["texte"], fait
    assert fait["lien"] == "https://drive.google.com/drive/trash"
    assert sorted(f["p"] for f in faux.lire()["corbeille"]) == ["Envoi/Copie de Vacances.mp4", "Factures/mars.pdf", "Vacances (1).mp4"]
    assert _post(s, "ranger", drive="gdrive").get("erreur"), "une confirmation ne sert qu'une fois"
    assert _commandes(faux.lire()["appels"]).count("delete") == 1


@pytest.mark.parametrize("cle, type_, drapeau", [("gdrive", "drive", "--drive-use-trash=true"),
                                                  ("onedrive", "onedrive", "--onedrive-hard-delete=false"), ("dropbox", "dropbox", None)])
def test_corbeille_seulement(faux, ecran, monkeypatch, cle, type_, drapeau):
    s, _ = ecran
    monkeypatch.setenv("RCLONE_DRIVE_USE_TRASH", "false")  # un réglage du dehors ne doit rien changer
    monkeypatch.setenv("RCLONE_ONEDRIVE_HARD_DELETE", "true")
    faux(cle, type_, fichiers=FICHIERS, about={})
    _post(s, "preparer", drive=cle)
    assert _post(s, "ranger", drive=cle).get("fait")
    appels = faux.lire()["appels"]
    (sup,) = [a for a in appels if a["argv"][0] == "delete"]
    assert sup["argv"][sup["argv"].index("--max-delete") + 1] == "3", "plafond = la liste exacte"
    assert drapeau is None or drapeau in sup["argv"]
    assert not any(x in sup["argv"] for x in ("--drive-use-trash=false", "--onedrive-hard-delete=true", "--onedrive-hard-delete"))
    assert all(a["env"] == [] for a in appels), "variables RCLONE_* transmises à rclone"
    assert set(_commandes(appels)) <= {"lsjson", "delete"}, "purge, cleanup, rmdirs… interdits"


@pytest.mark.parametrize("type_", ["alias", "local", "sftp"])
def test_service_sans_corbeille_refuse(faux, ecran, type_):
    s, _ = ecran
    faux("gdrive", type_, fichiers=FICHIERS, about={})
    assert _post(s, "preparer", drive="gdrive")["confirmer"]
    rep = _post(s, "ranger", drive="gdrive")
    assert rep.get("erreur") and "pas de corbeille" in rep["texte"]
    assert "delete" not in _commandes(faux.lire()["appels"]) and len(faux.lire()["fichiers"]) == len(FICHIERS)


def test_le_drive_a_change_entre_apercu_et_corbeille(faux, ecran):
    s, _ = ecran
    faux(fichiers=FICHIERS, about={})
    _post(s, "preparer", drive="gdrive")
    e = faux.lire()
    e["fichiers"] = [f for f in e["fichiers"] if f["p"] not in ("Vacances.mp4", "mars.pdf")]  # les exemplaires gardés ont disparu
    faux.ecrire(e)
    rep = _post(s, "ranger", drive="gdrive")
    assert rep.get("erreur") and "rien n'a été supprimé" in rep["texte"], "la dernière copie serait partie à la corbeille"
    assert "delete" not in _commandes(faux.lire()["appels"])


def test_jeton_jamais_affiche_ni_journalise(faux, ecran, capfd):
    s, url = ecran
    faux(fichiers=FICHIERS, about={})
    drives.conf().unlink()
    rep = _post(s, "connecter", drive="gdrive")
    assert rep.get("connecte") and JETON in drives.conf().read_text(), "la connexion doit être enregistrée par rclone"
    assert stat.S_IMODE(drives.conf().parent.stat().st_mode) & 0o077 == 0 or os.name == "nt", "dossier de config lisible par d'autres"
    e = faux.lire()
    e["panne"] = True
    faux.ecrire(e)
    panne = _post(s, "analyser", drive="gdrive")
    page = DIRECT.open(url, timeout=10).read().decode()
    sortie = capfd.readouterr()
    for vu in (json.dumps(rep), json.dumps(panne), page, sortie.out, sortie.err):
        assert JETON not in vu, "le jeton de connexion est sorti"
    assert panne.get("erreur") and "ne répond pas" in panne["texte"]


def test_restaurer_dit_la_verite(faux, ecran):
    s, _ = ecran
    faux("dropbox", "dropbox")
    rep = _post(s, "restaurer", drive="dropbox")
    assert rep["lien"] == "https://www.dropbox.com/deleted_files" and "corbeille de Dropbox" in rep["texte"]
    assert faux.lire().get("appels", []) == [], "restaurer ne fait rien à la place de l'utilisateur"


def test_pas_connecte_pas_d_analyse(faux, ecran):
    s, _ = ecran
    faux(fichiers=FICHIERS)
    drives.conf().unlink()
    assert "Connecte d'abord" in _post(s, "analyser", drive="gdrive")["texte"]
    assert _post(s, "analyser", drive="icloud-pirate")["erreur"]


# ---- Vrai rclone (s'il est là) sur un remote alias LOCAL : aucun compte en ligne --------------------------------
@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone absent (moteur inclus dans l'app, pas dans la suite)")
def test_vrai_rclone_sur_banc_local(maison, tmp_path, monkeypatch, capsys):
    jeu = tmp_path / "banc"
    for rel, octets in {"a.jpg": b"A" * 3000, "sous/a (1).jpg": b"A" * 3000, "b.txt": b"B" * 10}.items():
        (jeu / rel).parent.mkdir(parents=True, exist_ok=True)
        (jeu / rel).write_bytes(octets)
    remote_local.principal(["--racine", str(jeu)])
    capsys.readouterr()
    monkeypatch.setattr(drives, "conf", lambda: jeu / "rclone.conf")
    monkeypatch.setitem(drives.DRIVES, "savespace-banc", ("Banc", "drive", "md5", ["--drive-use-trash=true"], "x"))
    r = drives.analyser("savespace-banc", app._original_d_abord, 200)["resultat"]
    assert (r["groupes"], r["doublons"][0]["en_trop"]) == (1, ["sous/a (1).jpg"]) and r["espace"].startswith("Espace utilisé")
    plan, _ = drives.preparer("savespace-banc", app._original_d_abord, 200)
    avant = _photo(jeu)
    with pytest.raises(drives.Refus, match="pas de corbeille"):  # alias = disque local : aucune corbeille
        drives.ranger("savespace-banc", plan)
    assert _photo(jeu) == avant
    monkeypatch.setattr(drives, "conf", lambda: tmp_path / "config" / "rclone.conf")
    (tmp_path / "config").mkdir()
    assert drives._rclone("config", "create", "essai", "alias", "remote", str(jeu)).returncode == 0
    assert stat.S_IMODE((tmp_path / "config" / "rclone.conf").stat().st_mode) == 0o600, "rclone crée sa config en 600"
