"""Ranger en dossiers (rangement.py). Hermétique : HOME jetable, faux arbres sous tmp_path, faux rclone
(tests/faux_rclone.py) ou vrai rclone sur un remote alias LOCAL. Aucun vrai compte, aucun vrai disque du propriétaire.
Chaque garantie a ici un témoin, et dans tests/mutants.py le changement de code qui la trahit et doit rendre ce fichier ROUGE."""
import errno, json, os, shutil, subprocess, sys, textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from savespace_drive import app, drives, rangement, remote_local  # noqa: E402
from savespace_drive.chemins import SF_DATALESS  # noqa: E402
from test_app import DIRECT, ecran, maison  # noqa: E402,F401
from test_drives import _nuage, _post, faux  # noqa: E402,F401

SRC = Path(__file__).resolve().parents[1] / "src"
AN_2021, AN_2024 = 1_612_000_000, 1_712_000_000  # février 2021, avril 2024
ARBRE = {  # chemin : (octets, date) — un dossier « Téléchargements » en vrac, comme on en trouve partout
    "IMG_0412.jpg": (b"photo-1", AN_2024), "IMG_0413.HEIC": (b"photo-2", AN_2021), "Capture d’écran 2024-03-01.png": (b"cap", AN_2024),
    "Facture électricité mars.pdf": (b"facture", AN_2024), "CV Marie 2024.pdf": (b"cv", AN_2024), "passeport scan.jpg": (b"pp", AN_2021),
    "notes réunion.txt": (b"notes", AN_2021), "budget.xlsx": (b"budget", AN_2024), "film anniversaire.mov": (b"film", AN_2024),
    "Installer Zoom.pkg": (b"pkg", AN_2024), "photos-mariage.zip": (b"zip", AN_2021), "truc.xyz": (b"?", AN_2021),
    "Vacances Rome/plage.jpg": (b"r1", AN_2021), "Vacances Rome/hotel.pdf": (b"r2", AN_2021), "Vacances Rome/jour 2/x.jpg": (b"r3", AN_2021),
    "Impôts 2023/avis.pdf": (b"avis", AN_2024), "Photos/vieux.jpg": (b"v", AN_2021), "Photos/2019/a.jpg": (b"a", AN_2021),
    "Musique/Concert.m4a": (b"concert", AN_2021),
    # zones protégées : jamais déplacées, ni ce qu'elles contiennent
    "Google Photos/p.jpg": (b"gp", AN_2021), "Sauvegarde iPhone/manifest.db": (b"bk", AN_2021),
    "Photos Library.photoslibrary/database/x.db": (b"lib", AN_2021), "Projet/.git/HEAD": (b"ref", AN_2021), "Projet/main.py": (b"py", AN_2021),
    ".cache/x": (b"c", AN_2021), ".DS_Store": (b"ds", AN_2021),
}


def _poser(racine, arbre=ARBRE):
    for rel, (octets, t) in arbre.items():
        p = racine / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(octets)
        os.utime(p, (t, t))
    (racine / "Vide").mkdir()
    os.symlink("notes réunion.txt", racine / "lien vers notes")
    return racine


def _etat(racine):
    """L'état exact : chaque fichier (octets + date), chaque dossier, chaque lien."""
    out = {}
    for h, ds, fs in os.walk(racine):
        for n in ds + fs:
            p = Path(h) / n
            rel = p.relative_to(racine).as_posix()
            out[rel] = ("lien", os.readlink(p)) if p.is_symlink() else ("dossier",) if p.is_dir() else (p.read_bytes(), p.stat().st_mtime)
    return out


@pytest.fixture
def lieu(maison, tmp_path):
    racine = _poser(tmp_path / "Telechargements")
    return rangement.Local(Path(os.path.realpath(racine)))


def _plan(lieu):
    return rangement.proposer(*lieu.lister())


def _ranger(lieu, plan=None, confirme=False):
    return rangement.ranger(lieu, plan or _plan(lieu), confirme, lambda *a: None)


def _cibles(plan):
    return {m[0]: m[1] for m in plan["moves"]}


# ---- La méthode du propriétaire (docs/RANGEMENT_METHODE.md) --------------------------------------------------
def test_la_methode_dix_dossiers_aucun_vrac(lieu):
    plan = _plan(lieu)
    c = _cibles(plan)
    assert c["CV Marie 2024.pdf"] == "01 - ADMINISTRATIF/Emploi/CV Marie 2024.pdf"
    assert c["passeport scan.jpg"] == "01 - ADMINISTRATIF/Identité/passeport scan.jpg"
    assert c["Impôts 2023"] == "01 - ADMINISTRATIF/Impôts 2023", "un ancien dossier part tel quel, nom gardé"
    assert c["Facture électricité mars.pdf"] == "02 - FACTURES & ABONNEMENTS/2024/Facture électricité mars.pdf"
    assert c["notes réunion.txt"] == "03 - DOCUMENTS/2021/notes réunion.txt"
    assert c["IMG_0412.jpg"] == "Photos/2024/IMG_0412.jpg", "le dossier « Photos » déjà là sert de catégorie (pas de doublon)"
    assert c["Capture d’écran 2024-03-01.png"] == "Photos/Captures d'écran/Capture d’écran 2024-03-01.png"
    assert c["Photos/vieux.jpg"] == "Photos/2021/vieux.jpg", "aucun fichier en vrac non plus DANS un dossier du haut"
    assert c["Vacances Rome"] == "Photos/Vacances Rome", "un dossier va là où vont la plupart de ses fichiers"
    assert c["film anniversaire.mov"] == "04 - VIDÉOS/2024/film anniversaire.mov"
    assert c["Installer Zoom.pkg"].endswith("LOGICIELS & COMPRESSÉS/Installateurs/Installer Zoom.pkg")
    assert c["photos-mariage.zip"].endswith("LOGICIELS & COMPRESSÉS/Fichiers compressés/photos-mariage.zip")
    assert c["truc.xyz"].endswith("DIVERS/2021/truc.xyz") and c["Musique/Concert.m4a"] == "Musique/2021/Concert.m4a"
    a = rangement.apercu(plan, "Téléchargements")
    assert a["vrac"] == 1, a  # seul le raccourci reste en haut, laissé exprès
    assert len(a["arbre"]) == 8 and a["dossiers_haut"] == 8 + 5, a  # ≤ 10 dossiers rangés + les 5 zones laissées en place
    assert {x["chemin"] for x in a["arbre"]} >= {"01 - ADMINISTRATIF", "Photos"} and not any("Photos/2019" == m[1] for m in plan["moves"])


def test_deja_range_rien_a_faire_et_categories_numerotees_suivies(maison, tmp_path):
    """Les deux côtés : un lieu déjà rangé à la manière du propriétaire n'est pas dérangé."""
    racine = tmp_path / "Drive"
    _poser(racine, {"00 - ADMINISTRATIF & JURIDIQUE/Emploi/cv.pdf": (b"1", AN_2021), "04 - PERSO & PHOTOS/2021/a.jpg": (b"2", AN_2021),
                    "05 - VIDÉOS/Teaser/t.mp4": (b"3", AN_2021), "06 - VOYAGES/Rome/r.jpg": (b"4", AN_2021)})
    os.unlink(racine / "lien vers notes")
    lieu = rangement.Local(Path(os.path.realpath(racine)))
    assert _plan(lieu)["moves"] == [], "un lieu déjà rangé n'a rien à bouger"
    (racine / "nouvelle.jpg").write_bytes(b"5")
    os.utime(racine / "nouvelle.jpg", (AN_2024, AN_2024))
    (racine / "contrat bail.pdf").write_bytes(b"6")
    c = _cibles(_plan(lieu))
    assert c == {"nouvelle.jpg": "04 - PERSO & PHOTOS/2024/nouvelle.jpg",
                 "contrat bail.pdf": "00 - ADMINISTRATIF & JURIDIQUE/Logement/contrat bail.pdf"}, c


def test_jamais_un_nom_deja_pris_suffixe(maison, tmp_path):
    racine = tmp_path / "jeu"
    _poser(racine, {"a.jpg": (b"neuf", AN_2024), "Photos/2024/a.jpg": (b"ancien", AN_2024), "2024": (b"fichier", AN_2024)})
    lieu = rangement.Local(Path(os.path.realpath(racine)))
    plan = _plan(lieu)
    assert _cibles(plan)["a.jpg"] == "Photos/2024/a (2).jpg"
    _ranger(lieu, plan)
    assert (racine / "Photos/2024/a.jpg").read_bytes() == b"ancien" and (racine / "Photos/2024/a (2).jpg").read_bytes() == b"neuf"


# ---- Zones protégées, iCloud, rien d'ouvert ------------------------------------------------------------------
PROTEGES = ["Google Photos", "Sauvegarde iPhone", "Photos Library.photoslibrary", "Projet", ".cache", ".DS_Store", "lien vers notes", "Vide"]


def test_zones_protegees_jamais_touchees(lieu):
    avant = _etat(lieu.racine)
    plan = _plan(lieu)
    assert not any(m[0].split("/")[0] in PROTEGES for m in plan["moves"]), plan["moves"]
    laisses = dict(rangement.apercu(plan, "x")["laisses"])
    assert laisses["Google Photos"] == "zone protégée" and laisses["Sauvegarde iPhone"] == "sauvegarde"
    assert laisses["Photos Library.photoslibrary"] == "dossier d'app" and laisses["Projet"] == "fichier sensible"
    _ranger(lieu, plan)
    apres = _etat(lieu.racine)
    for c, v in avant.items():
        if c.split("/")[0] in PROTEGES:
            assert apres.get(c) == v, f"zone protégée touchée : {c}"


@pytest.mark.parametrize("drapeaux", [{"st_flags": SF_DATALESS}, {"st_file_attributes": 0x400000}], ids=["mac", "windows"])
def test_seulement_dans_icloud_jamais_ouvert_ni_deplace(lieu, monkeypatch, drapeaux):
    avant = _etat(lieu.racine)
    ouverts = _nuage(monkeypatch, lieu.racine, ["IMG_0413.HEIC", "Vacances Rome/jour 2/x.jpg"], **drapeaux)
    plan = _plan(lieu)
    laisses = dict(rangement.apercu(plan, "x")["laisses"])
    assert laisses == {**laisses, "IMG_0413.HEIC": "seulement dans iCloud", "Vacances Rome": "seulement dans iCloud"}
    _ranger(lieu, plan)
    ouverts = list(ouverts)
    monkeypatch.undo()  # pour relire l'état, le test lui-même doit ouvrir les fichiers
    apres = _etat(lieu.racine)
    assert apres["IMG_0413.HEIC"] == avant["IMG_0413.HEIC"] and apres["Vacances Rome/jour 2/x.jpg"] == avant["Vacances Rome/jour 2/x.jpg"]
    assert apres["Vacances Rome/plage.jpg"] == avant["Vacances Rome/plage.jpg"], "le dossier qui contient un fichier du nuage reste entier"
    assert ouverts == [], f"fichier seulement dans iCloud ouvert (donc téléchargé) : {ouverts}"
    assert (lieu.racine / "03 - DOCUMENTS/2021/notes réunion.txt").exists(), "le reste a bien été rangé"


def test_renvoye_au_nuage_entre_apercu_et_rangement(lieu, monkeypatch):
    plan = _plan(lieu)
    ouverts = _nuage(monkeypatch, lieu.racine, ["budget.xlsx", "Vacances Rome/plage.jpg"], st_flags=SF_DATALESS)
    texte = _ranger(lieu, plan)
    assert (lieu.racine / "budget.xlsx").exists() and (lieu.racine / "Vacances Rome/plage.jpg").exists()
    assert "2 éléments n'a pas pu bouger" in texte and ouverts == []


def test_le_plan_ne_lit_que_la_liste(lieu, monkeypatch):
    vrai_open, lus = open, []
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: lus.append(str(p)) or vrai_open(p, *a, **k))
    plan = _plan(lieu)
    rangement.apercu(plan, "x")
    assert lus == [] and plan["moves"], f"le plan a ouvert des fichiers : {lus}"


# ---- Déplacer : jamais d'écrasement, jamais de copie ---------------------------------------------------------
def test_jamais_d_ecrasement_meme_si_la_place_est_prise_apres_l_apercu(lieu):
    plan = _plan(lieu)
    pris = lieu.racine / _cibles(plan)["notes réunion.txt"]
    pris.parent.mkdir(parents=True)
    pris.write_bytes("un autre fichier, apparu depuis l'aperçu".encode())
    (lieu.racine / "01 - ADMINISTRATIF/Impôts 2023").mkdir(parents=True)  # même un dossier vide n'est jamais remplacé
    texte = _ranger(lieu, plan)
    assert pris.read_bytes() == "un autre fichier, apparu depuis l'aperçu".encode(), "fichier écrasé"
    assert (lieu.racine / "notes réunion.txt").read_bytes() == b"notes" and (lieu.racine / "Impôts 2023/avis.pdf").exists()
    assert list((lieu.racine / "01 - ADMINISTRATIF/Impôts 2023").iterdir()) == [], "dossier vide remplacé"
    assert "n'a pas pu bouger" in texte


def test_jamais_de_copie_hors_du_disque(lieu, monkeypatch):
    def autre_disque(s, d):
        raise OSError(errno.EXDEV, "autre disque")
    monkeypatch.setattr(rangement, "_renommer", autre_disque)
    avant = _etat(lieu.racine)
    _ranger(lieu)
    apres = {c: v for c, v in _etat(lieu.racine).items() if v != ("dossier",)}
    assert apres == {c: v for c, v in avant.items() if v != ("dossier",)}, "un fichier a été copié au lieu d'être renommé"


# ---- Journal, annuler, coupure -------------------------------------------------------------------------------
def test_annuler_remet_tout_exactement(lieu):
    avant = _etat(lieu.racine)
    _ranger(lieu)
    assert _etat(lieu.racine) != avant and not (lieu.racine / "IMG_0412.jpg").exists()
    texte = rangement.annuler(lieu, lambda *a: None)
    assert _etat(lieu.racine) == avant, "l'annulation n'a pas tout remis à l'identique (fichiers, dates, dossiers)"
    assert texte.startswith("Tout est revenu à sa place : 16 éléments")
    with pytest.raises(drives.Refus, match="Aucun rangement"):
        rangement.annuler(lieu, lambda *a: None)


class Coupure(BaseException):
    pass


def _couper_au(monkeypatch, k, apres):
    """Arrêt brutal au k-ième déplacement : juste avant, ou juste après qu'il a eu lieu (avant d'être noté « fait »)."""
    vrai, n = rangement._renommer, [0]

    def renommer(s, d):
        n[0] += 1
        if n[0] == k and not apres:
            raise Coupure
        vrai(s, d)
        if n[0] == k:
            raise Coupure
    monkeypatch.setattr(rangement, "_renommer", renommer)
    return lambda: monkeypatch.setattr(rangement, "_renommer", vrai)


@pytest.mark.parametrize("apres", [False, True], ids=["avant-le-deplacement", "apres-le-deplacement"])
def test_coupure_au_milieu_puis_annuler(lieu, monkeypatch, apres):
    avant = _etat(lieu.racine)
    retablir = _couper_au(monkeypatch, 5, apres)
    with pytest.raises(Coupure):
        _ranger(lieu)
    retablir()
    e = rangement.etat(lieu)
    assert e["phase"] == "interrompu" and len(e["fait"]) == 4
    rangement.annuler(lieu, lambda *a: None)
    assert _etat(lieu.racine) == avant, "après une coupure, l'annulation n'a pas tout remis"


@pytest.mark.parametrize("apres", [False, True], ids=["avant-le-deplacement", "apres-le-deplacement"])
def test_coupure_au_milieu_puis_reprendre(lieu, monkeypatch, tmp_path, apres):
    temoin = rangement.Local(Path(os.path.realpath(_poser(tmp_path / "temoin"))))
    _ranger(temoin)
    attendu = _etat(temoin.racine)
    retablir = _couper_au(monkeypatch, 5, apres)
    with pytest.raises(Coupure):
        _ranger(lieu)
    retablir()
    texte = rangement.reprendre(lieu, lambda *a: None)
    assert _etat(lieu.racine) == attendu and "n'a pas pu" not in texte, texte
    assert rangement.etat(lieu)["phase"] == "fait"
    rangement.annuler(lieu, lambda *a: None)
    assert (lieu.racine / "IMG_0412.jpg").read_bytes() == b"photo-1" and not (lieu.racine / "Photos/2024").exists()


def test_vrai_arret_du_processus_puis_annuler(lieu, maison):
    """Un vrai arrêt brutal (le processus est tué au 6e déplacement), puis annuler dans un autre processus."""
    avant = _etat(lieu.racine)
    script = textwrap.dedent(f"""
        import os, sys; sys.path.insert(0, {str(SRC)!r})
        from pathlib import Path
        from savespace_drive import rangement
        vrai, n = rangement._renommer, [0]
        def renommer(s, d):
            vrai(s, d); n[0] += 1
            if n[0] == 6: os.kill(os.getpid(), 9)
        rangement._renommer = renommer
        lieu = rangement.Local(Path({str(lieu.racine)!r}))
        rangement.ranger(lieu, rangement.proposer(*lieu.lister()), False, lambda *a: None)
    """)
    p = subprocess.run([sys.executable, "-c", script], env={**os.environ, "HOME": str(maison)}, capture_output=True, text=True)
    assert p.returncode == -9, p.stderr
    assert rangement.etat(lieu)["phase"] == "interrompu" and len(rangement.etat(lieu)["fait"]) == 5
    rangement.annuler(lieu, lambda *a: None)
    assert _etat(lieu.racine) == avant


def test_journal_hors_du_lieu_et_ferme_aux_autres(lieu):
    _ranger(lieu)
    j = rangement.Journal(lieu.cle).chemin
    assert j.is_file() and not j.is_relative_to(lieu.racine)
    assert oct(j.parent.stat().st_mode & 0o777) == "0o700"
    lignes = [json.loads(l) for l in j.read_text(encoding="utf-8").splitlines()]
    assert [list(o) for o in lignes[1:4]] == [["avant"], ["fait"], ["avant"]], "chaque déplacement est noté AVANT d'être fait"


def test_borne_au_dela_de_max_une_deuxieme_confirmation(lieu, monkeypatch):
    monkeypatch.setattr(rangement, "MAX", 3)
    avant = _etat(lieu.racine)
    with pytest.raises(drives.Refus, match="Confirme une 2e fois"):
        _ranger(lieu)
    assert _etat(lieu.racine) == avant
    _ranger(lieu, confirme=True)
    assert not (lieu.racine / "IMG_0412.jpg").exists()


# ---- Aperçu modifiable ---------------------------------------------------------------------------------------
def test_renommer_fusionner_exclure(lieu):
    plan = _plan(lieu)
    rangement.modifier(plan, "renommer", "04 - VIDÉOS", "Films de famille")
    assert _cibles(plan)["film anniversaire.mov"] == "Films de famille/2024/film anniversaire.mov"
    rangement.modifier(plan, "fusionner", "03 - DOCUMENTS", "01 - ADMINISTRATIF")
    assert _cibles(plan)["notes réunion.txt"] == "01 - ADMINISTRATIF/2021/notes réunion.txt"
    rangement.modifier(plan, "exclure", "Photos/Vacances Rome")
    assert "Vacances Rome" not in _cibles(plan) and "IMG_0412.jpg" in _cibles(plan)
    for op, chemin, nom in [("renommer", "Photos", "X"), ("renommer", "Films de famille", "a/b"), ("fusionner", "01 - ADMINISTRATIF", "Rien")]:
        with pytest.raises(drives.Refus):
            rangement.modifier(plan, op, chemin, nom)
    _ranger(lieu, plan)
    assert (lieu.racine / "Vacances Rome/plage.jpg").exists() and (lieu.racine / "Films de famille/2024/film anniversaire.mov").exists()


def test_jamais_dans_un_dossier_qui_bouge_lui_meme(lieu):
    plan = _plan(lieu)
    rangement.modifier(plan, "renommer", "04 - VIDÉOS", "Impôts 2023")  # le nom d'un dossier qui part lui-même ailleurs
    assert "film anniversaire.mov" not in _cibles(plan) and plan["conflits"] == {"film anniversaire.mov": "conflit de nom"}
    _ranger(lieu, plan)
    assert (lieu.racine / "film anniversaire.mov").exists() and (lieu.racine / "01 - ADMINISTRATIF/Impôts 2023/avis.pdf").exists()


def test_ecran_rien_ne_bouge_sans_le_oui(lieu, ecran):
    s, url = ecran
    page = DIRECT.open(url, timeout=10).read().decode()
    assert "Ranger" in page and "en dossiers…" in page and "Oui, ranger" in page and "pCloud" in page
    avant = _etat(lieu.racine)
    assert "Clique d'abord" in _post(s, "rangement_go", dossier=str(lieu.racine))["texte"]
    d = _post(s, "rangement_plan", dossier=str(lieu.racine))
    assert d["apercu"]["nombre"] == 16 and _etat(lieu.racine) == avant, "l'aperçu a bougé quelque chose"
    d = _post(s, "rangement_modifier", dossier=str(lieu.racine), op="exclure", chemin="04 - VIDÉOS")
    assert d["apercu"]["nombre"] == 15
    fait = _post(s, "rangement_go", dossier=str(lieu.racine))
    assert fait.get("fait") and fait["texte"].startswith("C'est fait : 15 éléments rangés"), fait
    assert (lieu.racine / "film anniversaire.mov").exists()
    assert "Clique d'abord" in _post(s, "rangement_go", dossier=str(lieu.racine))["texte"], "une confirmation ne sert qu'une fois"
    assert _post(s, "rangement_plan", dossier=str(lieu.racine))["annulable"] is True
    assert _post(s, "rangement_annuler", dossier=str(lieu.racine)).get("restaure") and _etat(lieu.racine) == avant


# ---- Drives (faux rclone) : liste seulement, côté serveur, jamais d'écrasement --------------------------------
DRIVE = [{"p": "IMG_0412.jpg", "t": 4_000, "h": "a", "d": "2024-04-01T10:00:00Z"}, {"p": "Facture mars.pdf", "t": 300, "h": "b"},
         {"p": "Vacances/plage.jpg", "t": 3_000, "h": "c"}, {"p": "Vacances/plage 2.jpg", "t": 3_000, "h": "d"},
         {"p": "Notes", "t": -1}, {"p": "Google Photos/p.jpg", "t": 9, "h": "e"}, {"p": "Apps/rclone/x", "t": 1, "h": "f"},
         {"p": "deux.pdf", "t": 1, "h": "g"}, {"p": "deux.pdf", "t": 2, "h": "h"}]
PERMIS = {"lsjson", "backend", "moveto", "rmdir"}


def _faux_etat(faux):
    e = faux.lire()
    return sorted((f["p"], f.get("h")) for f in e["fichiers"]), sorted(e.get("dossiers", []))


def test_drive_plan_ranger_annuler(faux, ecran):
    s, _ = ecran
    faux(fichiers=json.loads(json.dumps(DRIVE)), dossiers=["Vide"])
    avant = _faux_etat(faux)
    d = _post(s, "rangement_plan", drive="gdrive")
    assert set(a["argv"][0] for a in faux.lire()["appels"]) == {"lsjson"}, "le plan n'a fait que lire la liste"
    a = d["apercu"]
    assert dict(a["laisses"]) == {"Apps": "zone protégée", "Google Photos": "zone protégée", "Vide": "dossier vide",
                                  "deux.pdf": "deux éléments au même nom"}, a["laisses"]
    assert {x[0]: x[1] for x in a["exemples"]} == {"Facture mars.pdf": "01 - FACTURES & ABONNEMENTS/2024/Facture mars.pdf",
                                                   "IMG_0412.jpg": "02 - PHOTOS & IMAGES/2024/IMG_0412.jpg",
                                                   "Notes": "03 - DIVERS/2024/Notes", "Vacances": "02 - PHOTOS & IMAGES/Vacances"}
    assert _post(s, "rangement_go", drive="gdrive").get("fait")
    assert ("02 - PHOTOS & IMAGES/Vacances/plage 2.jpg", "d") in _faux_etat(faux)[0]
    assert _post(s, "rangement_annuler", drive="gdrive").get("restaure")
    assert _faux_etat(faux) == avant, "l'annulation n'a pas tout remis sur le drive"
    appels = faux.lire()["appels"]
    assert set(a["argv"][0] for a in appels) <= PERMIS, "commande interdite (copie, téléchargement, suppression…)"
    assert all("--drive-skip-shortcuts" in a["argv"] for a in appels if a["argv"][0] == "lsjson" and "--stat" not in a["argv"]
               and "--files-only" not in a["argv"]), "les raccourcis (fichiers partagés avec moi) doivent rester hors de la liste"
    for a in appels:
        if a["argv"][0] == "moveto":
            assert "--ignore-existing" in a["argv"] and "--max-transfer 1B --cutoff-mode hard" in " ".join(a["argv"]), a["argv"]
    assert all(a["env"] == [] for a in appels)


def test_drive_jamais_d_ecrasement(faux, ecran):
    s, _ = ecran
    faux(fichiers=json.loads(json.dumps(DRIVE)))
    cible = dict(_post(s, "rangement_plan", drive="gdrive")["apercu"]["exemples"])["IMG_0412.jpg"]
    e = faux.lire()
    e["fichiers"].append({"p": cible, "t": 1, "h": "AUTRE"})  # apparu depuis l'aperçu
    faux.ecrire(e)
    fait = _post(s, "rangement_go", drive="gdrive")
    assert "n'a pas pu bouger" in fait["texte"], fait
    fichiers = _faux_etat(faux)[0]
    assert (cible, "AUTRE") in fichiers and ("IMG_0412.jpg", "a") in fichiers
    _post(s, "rangement_annuler", drive="gdrive")
    assert (cible, "AUTRE") in _faux_etat(faux)[0], "l'annulation a pris le fichier d'un autre"


def test_drive_sans_deplacement_cote_serveur_refuse(faux, ecran):
    s, _ = ecran
    faux(fichiers=json.loads(json.dumps(DRIVE)), features={"Move": True, "DirMove": False})
    _post(s, "rangement_plan", drive="gdrive")
    rep = _post(s, "rangement_go", drive="gdrive")
    assert rep.get("erreur") and "sans télécharger" in rep["texte"]
    assert "moveto" not in [a["argv"][0] for a in faux.lire()["appels"]]


# ---- Vrai rclone (s'il est là), sur un remote alias LOCAL --------------------------------------------------
avec_rclone = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone absent (moteur inclus dans l'app, pas dans la suite)")


@avec_rclone
def test_vrai_rclone_garde_aucune_copie_possible(maison, tmp_path, monkeypatch):
    """La garde de chaque déplacement : un déplacement qui devrait COPIER (ici vers un autre stockage) est refusé."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "gros.bin").write_bytes(os.urandom(200_000))
    (tmp_path / "rclone.conf").write_text(f"[a]\ntype = alias\nremote = {tmp_path / 'a'}\n")
    monkeypatch.setattr(drives, "conf", lambda: tmp_path / "rclone.conf")
    monkeypatch.setattr(drives, "rclone", lambda: shutil.which("rclone"))
    drives._rclone("moveto", "a:gros.bin", ":memory:b/gros.bin", "--ignore-existing", *rangement.GARDE)
    assert (tmp_path / "a" / "gros.bin").stat().st_size == 200_000, "le fichier est parti par copie : la garde ne mord pas"


@avec_rclone
def test_vrai_rclone_ranger_puis_annuler(maison, tmp_path, monkeypatch, capsys):
    jeu = _poser(tmp_path / "banc", {k: v for k, v in ARBRE.items() if not k.startswith("Photos Library")})
    os.unlink(jeu / "lien vers notes")
    remote_local.principal(["--racine", str(jeu)])
    capsys.readouterr()
    (jeu / "rclone.conf").rename(tmp_path / "rclone.conf")
    monkeypatch.setattr(drives, "conf", lambda: tmp_path / "rclone.conf")
    monkeypatch.setattr(drives, "rclone", lambda: shutil.which("rclone"))
    monkeypatch.setitem(drives.DRIVES, "savespace-banc", ("Banc", "alias", "md5", [], "x"))
    avant = _etat(jeu)
    lieu = rangement.Drive("savespace-banc")
    plan = _plan(lieu)
    assert _cibles(plan)["Vacances Rome"] == "Photos/Vacances Rome" and "Google Photos" not in _cibles(plan)
    texte = _ranger(lieu, plan)
    assert "n'a pas pu" not in texte and (jeu / "Photos/2024/IMG_0412.jpg").read_bytes() == b"photo-1"
    assert (jeu / "Photos/Vacances Rome/jour 2/x.jpg").exists() and _etat(jeu)["Google Photos/p.jpg"] == avant["Google Photos/p.jpg"]
    rangement.annuler(lieu, lambda *a: None)
    assert _etat(jeu) == avant, "le vrai rclone n'a pas tout remis à l'identique"
