"""APP0 (sortie lisible) et APP1 (écran local) — hermétiques : tout se passe sous tmp_path, HOME jetable."""
import io, json, os, re, shutil, sys, threading, urllib.error, urllib.request
from pathlib import Path

import pytest

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais de proxy : tout reste sur 127.0.0.1

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from savespace_drive import analyse, app, cli, lisible  # noqa: E402


@pytest.fixture
def maison(tmp_path, monkeypatch):
    h = tmp_path / "maison"
    (h / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


def _jeu(racine):
    """Petit dossier synthétique : 2 groupes de doublons, un fichier unique, un secret sous .ssh."""
    for rel, octets in {"a/photo.jpg": b"P" * 3000, "a/Copie de photo.jpg": b"P" * 3000, "b/photo (1).jpg": b"P" * 3000,
                        "doc.pdf": b"D" * 500, "z/doc.pdf": b"D" * 500, "unique.txt": b"U" * 42, ".ssh/id": b"D" * 500}.items():
        (racine / rel).parent.mkdir(parents=True, exist_ok=True)
        (racine / rel).write_bytes(octets)
    return racine


def _photo(racine):
    return {p.relative_to(racine).as_posix(): (p.read_bytes(), p.stat().st_mtime)
            for p in racine.rglob("*") if p.is_file() and p.relative_to(racine).parts[0] != app.QUARANTAINE}


class FauxTerminal(io.StringIO):
    def isatty(self):
        return True


def _cli(monkeypatch, argv, terminal):
    vrai, sys.stdout = sys.stdout, (FauxTerminal() if terminal else io.StringIO())
    try:
        rc = cli.main(argv)
    finally:
        sortie, sys.stdout = sys.stdout, vrai
    return rc, sortie.getvalue()


# ---- APP0 : sortie lisible -------------------------------------------------------------------------------
def test_tailles_en_francais():
    assert [lisible.taille(o) for o in (1, 999, 1000, 8_500_000, 1_330_000_000)] == \
        ["1 octet", "999 octets", "1,0 Ko", "8,5 Mo", "1,3 Go"]
    assert lisible.court("a/b/c/d/e.txt") == "a/…/d/e.txt" and lisible.court("a/b.txt") == "a/b.txt"


def test_json_inchange_et_lisible_dans_un_terminal(tmp_path, maison, monkeypatch, capsys):
    racine = _jeu(tmp_path / "jeu")
    analyse.principal(["--racine", str(racine)])
    attendu = capsys.readouterr().out
    rc1, brut = _cli(monkeypatch, ["analyse", "--racine", str(racine), "--json"], terminal=True)
    rc2, redirige = _cli(monkeypatch, ["analyse", "--racine", str(racine)], terminal=False)
    rc3, texte = _cli(monkeypatch, ["analyse", "--racine", str(racine)], terminal=True)
    assert rc1 == rc2 == rc3 == 0
    assert brut == redirige == attendu and json.loads(attendu)["recuperables_octets"] == 6500
    assert "Tu peux récupérer 6,5 Ko" in texte and "Groupe 2" in texte and "sha256" not in texte and "{" not in texte


@pytest.mark.parametrize("argv", [["doctor"], ["doublons", "--racine", "JEU"], ["gros", "--top", "3"],
                                  ["similaires", "JEU"],
                                  pytest.param(["range", "JEU"], marks=pytest.mark.skipif(shutil.which("rclone") is None, reason="range exige rclone (moteur optionnel)"))])
def test_aucune_commande_n_affiche_de_json_brut_dans_un_terminal(tmp_path, maison, monkeypatch, argv):
    racine = _jeu(tmp_path / "jeu")
    avant = _photo(racine)
    monkeypatch.chdir(racine)
    rc, texte = _cli(monkeypatch, [str(racine) if a == "JEU" else a for a in argv], terminal=True)
    assert rc == 0 and texte.strip() and not any(l.lstrip().startswith("{") for l in texte.splitlines()), texte
    assert not re.search(r"\(\d+ o\)|^g\d+ : |octets=", texte, re.M), f"ligne brute non traduite : {texte}"
    assert _photo(racine) == avant, "une commande à blanc a modifié le dossier"


def test_invite_de_confirmation_traduite():
    vue = io.StringIO()
    t = lisible.Traducteur("caches", [], vue)
    t.write("cibles=3 octets=4500\no/N : ")
    t.flush()
    assert vue.getvalue() == ("3 fichiers (caches, journaux, vieux téléchargements, installeurs) iraient à la corbeille : 4,5 Ko.\n"
                              + lisible.CONFIRMER)


# ---- APP1 : écran local ----------------------------------------------------------------------------------
@pytest.fixture
def ecran(maison):
    s, url = app.creer_serveur()
    fil = threading.Thread(target=lambda: [s.handle_request() for _ in iter(lambda: s.fini, True)], daemon=True)
    fil.start()
    yield s, url
    s.fini = True
    fil.join(5)
    s.server_close()


def _post(s, action, dossier="", jeton=None, hote=None):
    req = urllib.request.Request(f"http://127.0.0.1:{s.server_port}/{action}", json.dumps({"dossier": str(dossier)}).encode(),
                                 {"X-Jeton": jeton or s.jeton, "Host": hote or s.hote})
    with DIRECT.open(req, timeout=30) as r:
        return json.loads(r.read())


def test_ecran_local_seulement_et_protege(ecran, maison):
    s, url = ecran
    assert s.server_address[0] == "127.0.0.1" and url.startswith("http://127.0.0.1:")
    page = DIRECT.open(url, timeout=10).read().decode()
    assert "Téléchargements" in page and "Bureau" not in page and "Analyser" in page and "Annuler / restaurer" in page
    for essai in (lambda: DIRECT.open(url.split("?")[0], timeout=10),
                  lambda: _post(s, "analyser", maison / "Downloads", jeton="faux"),
                  lambda: _post(s, "analyser", maison / "Downloads", hote="evil.example:80")):
        with pytest.raises(urllib.error.HTTPError) as e:
            essai()
        assert e.value.code == 403


def test_ecran_refuse_maison_racine_et_vide(ecran, maison):
    s, _ = ecran
    avant = sorted(maison.rglob("*"))
    for dossier in (maison, "/", Path(maison.anchor), "", maison / "absent"):
        rep = _post(s, "preparer", dossier)
        assert rep.get("erreur") and not rep.get("confirmer"), (dossier, rep)
    assert sorted(maison.rglob("*")) == avant


def test_ecran_analyser_ranger_restaurer_aller_retour(ecran, tmp_path):
    s, _ = ecran
    racine = _jeu(tmp_path / "jeu")
    avant = _photo(racine)
    assert "Tu peux récupérer 6,5 Ko" in _post(s, "analyser", racine)["texte"]
    assert _post(s, "ranger", racine).get("erreur"), "ranger sans aperçu doit être refusé"
    apercu = _post(s, "preparer", racine)
    assert apercu["confirmer"] and _photo(racine) == avant, "l'aperçu ne doit rien bouger"
    en_trop = ["a/Copie de photo.jpg", "b/photo (1).jpg", "z/doc.pdf"]  # l'écran garde l'original : pas une copie, le moins profond
    assert all(f"mis de côté : {c}" in apercu["texte"] for c in en_trop) and apercu["texte"].count("mis de côté :") == 3
    assert ".ssh" not in apercu["texte"] and "unique.txt" not in apercu["texte"]
    assert _post(s, "ranger", tmp_path).get("erreur"), "l'aperçu d'un dossier ne vaut pas pour un autre"
    fait = _post(s, "ranger", racine)
    assert not fait.get("erreur") and "3 fichiers mis de côté" in fait["texte"], fait
    apres = _photo(racine)
    assert sorted(set(avant) - set(apres)) == sorted(en_trop) and all(apres[k] == avant[k] for k in apres)
    assert list((racine / app.QUARANTAINE).glob("*/manifeste.json")), "pas de manifeste : pas de retour possible"
    assert _post(s, "ranger", racine).get("erreur"), "une confirmation ne sert qu'une fois"
    assert "Aucun doublon trouvé" in _post(s, "analyser", racine)["texte"], "les fichiers mis de côté recomptés comme doublons"
    vide = _post(s, "preparer", racine)
    assert "Aucun doublon à ranger" in vide["texte"] and not vide.get("confirmer"), "bouton de confirmation sans rien à ranger"
    rep = _post(s, "restaurer", racine)
    assert not rep.get("erreur") and "3 fichiers remis" in rep["texte"], rep
    assert _photo(racine) == avant, "la restauration ne rend pas l'arbre identique (octets et dates)"
    assert _post(s, "restaurer", racine).get("erreur"), "rien à restaurer une seconde fois"


def test_quitter(ecran):
    s, _ = ecran
    assert "fermé" in _post(s, "quitter")["texte"] and s.fini
