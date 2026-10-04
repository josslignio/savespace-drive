"""Le test du test : chaque garantie des drives a un mutant (le code qui la trahit) ; la suite doit devenir ROUGE.
Usage : python tests/mutants.py   — copie src/ et tests/ dans build/mutants/<n>/, applique UN changement, lance pytest.
Témoin d'abord : la copie non mutée doit être verte. Un mutant qui reste vert = garantie décorative (code de sortie 1)."""
import shutil, subprocess, sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
D, A, C, DR = "analyse.py", "app.py", "chemins.py", "drives.py"
MUTANTS = [  # (garantie, fichier, avant, après)
    ("pas téléchargé : jamais ouvert (analyse)", D, "if dans_le_nuage(brut, st):", "if False:"),
    ("pas téléchargé : jamais ouvert (doublons)", "doublons.py", "if dans_le_nuage(brut, st):", "if False:"),
    ("pas téléchargé : drapeau macOS lu", C, "getattr(st, \"st_flags\", 0) & SF_DATALESS or ", ""),
    ("pas téléchargé : revérifié avant de ranger", A, "if any(_au_nuage(", "if False and any(_au_nuage("),
    ("iCloud Drive : seul coin de ~/Library ouvert", C, "if not r.is_relative_to(lib / \"Mobile Documents\" / \"com~apple~CloudDocs\"):", "if True:"),
    ("drive : rien n'est téléchargé", DR, "fichiers, p = _liste(cle), _rclone(\"about\"",
     "fichiers, p = _liste(cle), _rclone(\"hashsum\", \"md5\", \"--download\", f\"{cle}:\") and _rclone(\"about\""),
    ("drive : doublons par l'empreinte du service", DR, "(f.get(\"Hashes\") or {}).get(h)", "f.get(\"Size\")"),
    ("drive : rien ne part sans le oui", DR, "        return rep\n    if action == \"ranger\":",
     "        plans.get(\"drive:\" + cle) and ranger(cle, plans[\"drive:\" + cle])\n        return rep\n    if action == \"ranger\":"),
    ("drive : pas de corbeille sans aperçu", DR, "plans.pop(\"drive:\" + cle, None)",
     "plans.pop(\"drive:\" + cle, None) or _groupes(_liste(cle), garder)"),
    ("drive : corbeille forcée (Google Drive)", DR, "[\"--drive-use-trash=true\"]", "[]"),
    ("drive : corbeille forcée (OneDrive)", DR, "[\"--onedrive-hard-delete=false\"]", "[]"),
    ("drive : réglages RCLONE_* du dehors ignorés", DR, "if not k.startswith(\"RCLONE_\")", "if k"),
    ("drive : plafond = la liste exacte", DR, "\"--max-delete\", str(len(a_jeter))", "\"--max-delete\", \"-1\""),
    ("drive : sans corbeille = refusé", DR, "    if type_de(cle) != type_:  # alias", "    if False:  # alias"),
    ("drive : l'exemplaire gardé est encore là", DR, "if actuel.get(g[\"membres\"][0]) == (g[\"taille\"], g[\"empreinte\"])", "if True"),
    ("drive : même nom deux fois = jamais proposé", DR, "if vus[c] == 1 and not", "if not"),
    ("drive : jeton jamais affiché (erreur)", DR, "ne répond pas (code {p.returncode})", "ne répond pas ({p.stderr})"),
    ("drive : jeton jamais affiché (connexion)", DR, "    if p.returncode or type_de(cle) != type_:", "    print(p.stdout)\n    if p.returncode or type_de(cle) != type_:"),
    ("drive : dossier de config fermé aux autres", DR, "conf().parent.chmod(0o700)", "conf().parent.chmod(0o755)"),
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
    return p.returncode, (p.stdout.strip().splitlines() or [""])[-1]


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
