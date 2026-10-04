"""Le test du test : chaque garantie a un mutant (le code qui la trahit) ; la suite doit devenir ROUGE.
Usage : python tests/mutants.py   — copie src/ et tests/ dans build/mutants/<n>/, applique UN changement, lance pytest.
Témoin d'abord : la copie non mutée doit être verte. Un mutant qui reste vert = garantie décorative (code de sortie 1)."""
import shutil, subprocess, sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MUTANTS = [  # (garantie, fichier, avant, après)
    ("nuage : jamais ouvert (analyse)", "analyse.py", "            if dans_le_nuage(st):", "            if False:"),
    ("nuage : jamais ouvert (doublons)", "doublons.py", "if dans_le_nuage(st):  # pas sur ce disque : le lire le téléchargerait", "if False:"),
    ("nuage : jamais ouvert (similaires)", "similaires.py", "if not dans_le_nuage(st := os.stat(chemin)):", "if (st := os.stat(chemin)):"),
    ("nuage : jamais ouvert (caches)", "caches.py", "if dans_le_nuage(st := p.stat()): continue", "st = p.stat()"),
    ("nuage : jamais ouvert (range)", "range.py", " and not dans_le_nuage(os.stat(os.path.join(cible, f)))", ""),
    ("nuage : drapeau macOS lu", "chemins.py", "getattr(st, \"st_flags\", 0) & SF_DATALESS or ", ""),
    ("nuage : attribut Windows lu", "chemins.py", " or getattr(st, \"st_file_attributes\", 0) & A_LA_DEMANDE", ""),
    ("taille unique : jamais lue (analyse)", "analyse.py", "if tailles[taille] > 1 and not _protege(relatif)", "if not _protege(relatif)"),
    ("taille unique : jamais lue (doublons)", "doublons.py", "for b, t in candidats if tailles[t] > 1]", "for b, t in candidats]"),
    ("taille unique : jamais lue (similaires)", "similaires.py", "open(c, \"rb\").read() if tailles[t] > 1 else b\"\"", "open(c, \"rb\").read()"),
    ("nuage : revérifié avant de ranger (app)", "app.py", "if any(_au_nuage(", "if False and any(_au_nuage("),
    ("iCloud Drive : seul coin de ~/Library ouvert", "chemins.py", "if not r.is_relative_to(lib / \"Mobile Documents\" / \"com~apple~CloudDocs\"):", "if True:"),
    ("drive : rien n'est téléchargé", "drives.py", "fichiers, p = _liste(cle), _rclone(\"about\"",
     "fichiers, p = _liste(cle), _rclone(\"hashsum\", \"md5\", \"--download\", f\"{cle}:\") and _rclone(\"about\""),
    ("drive : doublons par l'empreinte du service", "drives.py", "(f.get(\"Hashes\") or {}).get(h)", "f.get(\"Size\")"),
    ("drive : rien ne part sans le oui", "drives.py", "        return rep\n    if action == \"ranger\":",
     "        plans.get(\"drive:\" + cle) and ranger(cle, plans[\"drive:\" + cle])\n        return rep\n    if action == \"ranger\":"),
    ("drive : pas de corbeille sans aperçu", "drives.py", "plans.pop(\"drive:\" + cle, None)",
     "plans.pop(\"drive:\" + cle, None) or _groupes(_liste(cle), garder)"),
    ("drive : corbeille forcée (Google Drive)", "drives.py", "[\"--drive-use-trash=true\"]", "[]"),
    ("drive : corbeille forcée (OneDrive)", "drives.py", "[\"--onedrive-hard-delete=false\"]", "[]"),
    ("drive : réglages RCLONE_* du dehors ignorés", "drives.py", "if not k.startswith(\"RCLONE_\")", "if k"),
    ("drive : plafond = la liste exacte", "drives.py", "\"--max-delete\", str(len(a_jeter))", "\"--max-delete\", \"-1\""),
    ("drive : sans corbeille = refusé", "drives.py", "    if type_de(cle) != type_:  # alias", "    if False:  # alias"),
    ("drive : l'exemplaire gardé est encore là", "drives.py", "if actuel.get(g[\"membres\"][0]) == (g[\"taille\"], g[\"empreinte\"])", "if True"),
    ("drive : même nom deux fois = jamais proposé", "drives.py", "if vus[c] == 1 and not", "if not"),
    ("drive : jeton jamais affiché (erreur)", "drives.py", "ne répond pas (code {p.returncode})", "ne répond pas ({p.stderr})"),
    ("drive : jeton jamais affiché (connexion)", "drives.py", "    if p.returncode or type_de(cle) != type_:", "    print(p.stdout)\n    if p.returncode or type_de(cle) != type_:"),
    ("drive : dossier de config fermé aux autres", "drives.py", "conf().parent.chmod(0o700)", "conf().parent.chmod(0o755)"),
]


def lancer(n, mutant=None):
    copie = RACINE / "build" / "mutants" / str(n)
    shutil.rmtree(copie, ignore_errors=True)
    for d in ("src", "tests"):
        shutil.copytree(RACINE / d, copie / d, ignore=shutil.ignore_patterns("__pycache__", "mutants.py"))
    shutil.copy(RACINE / "pytest.ini", copie)
    if mutant:
        f = copie / "src" / "savespace_drive" / mutant[1]
        texte = f.read_text(encoding="utf-8")
        assert texte.count(mutant[2]) == 1, f"mutant {n} : motif introuvable ou ambigu dans {mutant[1]}"
        f.write_text(texte.replace(mutant[2], mutant[3]), encoding="utf-8")
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"], cwd=copie,
                       capture_output=True, text=True)
    shutil.rmtree(copie, ignore_errors=True)
    fin = (p.stdout.strip().splitlines() or [""])[-1]
    return (p.returncode if " failed" in fin or p.returncode == 0 else 0), fin  # tué = un test ROUGE, pas une erreur de syntaxe


def principal():
    rc, fin = lancer(0)
    print(f"témoin (non muté) : {'VERT' if rc == 0 else 'ROUGE'} — {fin}")
    if rc:
        return 2
    survivants = 0
    for i, m in enumerate(MUTANTS, 1):
        rc, fin = lancer(i, m)
        survivants += rc == 0
        print(f"{i:2} {'tué   ' if rc else 'SURVIT'} {m[0]} — {fin}")
    print(f"score de mutation : {len(MUTANTS) - survivants}/{len(MUTANTS)} tués")
    return int(survivants > 0)


if __name__ == "__main__":
    sys.exit(principal())
