"""Hotfix 0.1.1 — Bureau et Documents synchronisés par iCloud : un fichier « seulement dans iCloud » (dataless) n'est
JAMAIS ouvert (l'ouvrir le télécharge, un par un : analyse bloquée 400 s mesurées, disque qui se remplit), et un fichier
de taille unique n'est jamais lu (aucun doublon possible). Hermétique : le drapeau macOS est simulé sur le stat."""
import builtins, io, json, os, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from savespace_drive import analyse, app, caches, doublons, range as range_  # noqa: E402
from savespace_drive.chemins import Garde, SF_DATALESS  # noqa: E402
from test_app import _cli, maison  # noqa: E402,F401

NUAGE = ["Bureau/photo.jpg", "Bureau/rapport.pdf", "Bureau/installeur.dmg"]  # mêmes octets que des fichiers présents


class Stat:  # le vrai stat, plus le drapeau que pose macOS sur un fichier resté dans iCloud
    def __init__(self, st, **drapeaux):
        self.__dict__.update(drapeaux, _st=st)

    def __getattr__(self, k):
        return getattr(self._st, k)


def _jeu(racine):
    for rel, octets in {"photo.jpg": b"P" * 4000, "Copie de photo.jpg": b"P" * 4000, "rapport.pdf": b"R" * 900,
                        "unique.txt": b"U" * 77, "seule.png": b"S" * 555, "autre.bin": b"A" * 1234, "installeur.dmg": b"I" * 300,
                        "Bureau/photo.jpg": b"P" * 4000, "Bureau/rapport.pdf": b"R" * 900, "Bureau/installeur.dmg": b"I" * 300}.items():
        (racine / rel).parent.mkdir(parents=True, exist_ok=True)
        (racine / rel).write_bytes(octets)
    return racine


@pytest.fixture
def espion(tmp_path, monkeypatch):
    """Fichiers NUAGE marqués « seulement dans iCloud » ; toute ouverture de fichier est notée."""
    racine = _jeu(Path(os.path.realpath(tmp_path)) / "jeu")
    cibles, ouverts, drapeaux = {str(racine / r) for r in NUAGE}, [], {"st_flags": SF_DATALESS}
    vrai_stat, vrai_open = os.stat, builtins.open

    def faux_stat(p, *a, **k):
        st = vrai_stat(p, *a, **k)
        return Stat(st, **drapeaux) if os.path.realpath(p) in cibles else st

    def faux_open(p, *a, **k):
        if isinstance(p, (str, os.PathLike)):
            ouverts.append(os.path.relpath(os.path.realpath(p), racine))
        return vrai_open(p, *a, **k)
    monkeypatch.setattr(os, "stat", faux_stat)
    monkeypatch.setattr(builtins, "open", faux_open)
    monkeypatch.setattr(io, "open", faux_open)
    return racine, ouverts, drapeaux


@pytest.mark.parametrize("drapeaux", [{"st_flags": SF_DATALESS}, {"st_file_attributes": 0x400000}], ids=["mac-icloud", "windows-onedrive"])
def test_seulement_dans_le_nuage_jamais_ouvert(espion, maison, monkeypatch, drapeaux):
    racine, ouverts, simules = espion
    simules.clear()
    simules.update(drapeaux)
    r = analyse.analyser(racine, 10)
    g = doublons.detecter(racine, Garde([racine]))
    _, apercu = app.preparer(racine)
    c = caches.cibles(racine, 30)
    monkeypatch.chdir(racine)
    rc_s, texte_s = _cli(monkeypatch, ["similaires", str(racine), "--json"], terminal=False)
    assert not [o for o in ouverts if o in NUAGE], f"ouverts donc téléchargés : {ouverts}"
    assert r["nuage_seulement"] == {"fichiers": 3, "octets": 5200}
    assert r["total_octets"] == 4000 * 2 + 900 + 77 + 555 + 1234 + 300, "le total ne compte que ce qui est sur ce disque"
    assert [x["chemins"] for x in r["doublons"]] == [["Copie de photo.jpg", "photo.jpg"]]
    assert not any(x.startswith("Bureau/") for x in r["caches"] + [y["chemin"] for y in r["gros"]])
    assert [x["membres"] for x in g] == [["Copie de photo.jpg", "photo.jpg"]] and [p.name for p in c] == ["installeur.dmg"]
    assert apercu["nombre"] == 1 and rc_s == 0 and "Bureau" not in texte_s
    texte = app.analyser(racine)
    assert "3 fichiers (5,2 Ko) sont seulement dans " in texte["texte"] and "rien n'a été téléchargé" in texte["texte"]
    assert texte["resultat"]["nuage"].startswith("3 fichiers (5,2 Ko) sont seulement dans ")
    assert range_.principal([str(racine / "Bureau"), "--oui"]) == 0 and not [o for o in ouverts if o in NUAGE], "range a lu le nuage"
    assert all((racine / x).is_file() for x in NUAGE), "un fichier resté dans iCloud a été déplacé"


def test_taille_unique_jamais_lue(espion, maison, monkeypatch):
    racine, ouverts, _ = espion
    analyse.analyser(racine, 10)
    doublons.detecter(racine, Garde([racine]))
    monkeypatch.chdir(racine)
    _cli(monkeypatch, ["similaires", str(racine), "--json"], terminal=False)
    for seul in ("unique.txt", "seule.png", "autre.bin", "rapport.pdf", "installeur.dmg"):  # tailles uniques une fois le nuage écarté
        assert seul not in ouverts, f"{seul} lu alors qu'aucun doublon n'est possible"
    assert {"photo.jpg", "Copie de photo.jpg"} <= set(ouverts), "les candidats de même taille doivent être comparés"


def test_json_et_texte_de_doublons(espion, maison, monkeypatch):
    racine, _, _ = espion
    rc, brut = _cli(monkeypatch, ["doublons", "--racine", str(racine), "--json"], terminal=False)
    d = json.loads(brut)
    assert rc == 0 and d["nuage_seulement"] == 3 and d["vides"] == 0 and len(d["groupes"]) == 1
    rc, texte = _cli(monkeypatch, ["doublons", "--racine", str(racine)], terminal=True)
    assert "3 fichiers sont seulement dans" in texte
