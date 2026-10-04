"""Commande « tout » — SaveSpace Drive, jalon DN6B (ROADMAP DN6, SPEC §1, §4). stdlib seule :
enchaîne par APPEL DIRECT au module analyse (gelé DN1A, manifeste jamais cru) les catégories
présentes à HEAD (doublons, caches, decharge, range absentes → ignorées), o/N sans --oui,
journalise la reprise (journal.json, effacé en fin), écrit savespace_tout/rapport_final.{json,txt}."""
import argparse, importlib.util, json, os, sys, time
from pathlib import Path
from savespace_drive import analyse
PHRASE = "La quarantaine reste sur le même volume : elle ne compte pas dans les Go réellement libérés."
def principal(argv=None):
    p = argparse.ArgumentParser(prog="savespace_drive.tout", description="Chaîne les catégories présentes à HEAD (DN6B).")
    p.add_argument("--racine", required=True, help="dossier cible ; refusé si « / » ou le HOME du processus")
    p.add_argument("--oui", action="store_true", help="enchaîne sans confirmation o/N"); a = p.parse_args(argv)
    racine = os.path.realpath(a.racine); interdits = {os.path.realpath("/")} | ({os.path.realpath(os.environ["HOME"])} if os.environ.get("HOME") else set())
    if not str(a.racine).strip() or racine in interdits:
        print(f"tout : refus — racine interdite : {a.racine} (racines refusées : / et HOME)", file=sys.stderr); return 2
    debut, sortie = time.monotonic(), Path(racine) / "savespace_tout"
    try: fait = json.loads((sortie / "journal.json").read_text(encoding="utf-8"))["fait"]; assert isinstance(fait, dict)
    except Exception: fait = {}
    r = fait.get("analyse")
    for nom in ("analyse", "doublons", "caches", "decharge", "range"):
        if importlib.util.find_spec("savespace_drive." + nom) is None: print(f"{nom} : absente à HEAD, ignorée"); continue
        if nom in fait: print(f"{nom} : déjà journalisée, sautée"); continue
        if not a.oui and (print(f"{nom} ? (o/N)", flush=True) or sys.stdin.readline().strip().lower() != "o"):
            print(f"{nom} : refusée"); continue
        r = fait[nom] = analyse.analyser(racine, 5); print(f"{nom} : faite")
        sortie.mkdir(parents=True, exist_ok=True); (sortie / "journal.json").write_text(json.dumps({"fait": fait}, sort_keys=True), encoding="utf-8")
    r = r if isinstance(r, dict) and "total_octets" in r else {"total_octets": 0, "recuperables_octets": 0, "doublons": [], "caches": []}
    go = {"doublons": round(r["recuperables_octets"] / 2**30, 2), "caches": round(sum((Path(racine) / c).stat().st_size for c in r["caches"]) / 2**30, 2)}
    rapport = {"go_par_source": {racine: round(r["total_octets"] / 2**30, 2)}, "go_recuperables": go, "go_reellement_liberes": 0.0, "duree_s": round(time.monotonic() - debut, 3), "ligne_partageable": f"SaveSpace Drive : {round(sum(go.values()), 2)} Go récupérables, {len(r['doublons'])} doublons, 0 fichier perdu"}
    sortie.mkdir(parents=True, exist_ok=True); (sortie / "rapport_final.json").write_text(json.dumps(rapport, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (sortie / "rapport_final.txt").write_text(rapport["ligne_partageable"] + "\n" + PHRASE + "\n", encoding="utf-8")
    (sortie / "journal.json").unlink(missing_ok=True); print(PHRASE)
    return 0
if __name__ == "__main__":
    sys.exit(principal())
