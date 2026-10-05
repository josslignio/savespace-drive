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
    ("drive : pas de corbeille sans aperçu", "drives.py", "(plan := plans.pop(\"drive:\" + cle, None))",
     "(plan := plans.pop(\"drive:\" + cle, None) or _groupes(_liste(cle), garder))"),
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
    ("drive : déconnecter retire vraiment le compte", "drives.py", "_rclone(\"config\", \"delete\", cle, delai=60)", "None"),
    ("drive : rclone de connexion tué à la fermeture", "app.py", "        drives.arreter()\n        super().server_close()", "        super().server_close()"),
    ("drive : une 2e connexion remplace la 1re", "drives.py", "    arreter()  # une connexion", "    pass  # une connexion"),
    ("drive : pCloud dans « Où chercher ? »", "drives.py", "    \"pcloud\": (\"pCloud\", \"pcloud\", \"sha1\", [], \"https://my.pcloud.com/#page=trash\"),", ""),
    # ---- ranger en dossiers (rangement.py, tests/test_rangement.py) ----
    ("ranger : le plan ne lit que la liste (Mac)", "rangement.py", "            st = os.stat(p, follow_symlinks=False)\n",
     "            st = os.stat(p, follow_symlinks=False)\n            open(p, 'rb').close() if os.path.isfile(p) else None\n"),
    ("ranger : le plan ne télécharge rien (drive)", "rangement.py", "    p = drives._rclone(\"lsjson\", \"-R\", \"--fast-list\"",
     "    drives._rclone(\"copy\", f\"{cle}:\", \"copie\")\n    p = drives._rclone(\"lsjson\", \"-R\", \"--fast-list\""),
    ("ranger : partagés (raccourcis) hors de la liste", "rangement.py", "\"--drive-skip-shortcuts\", ", ""),
    ("ranger : même nom deux fois = laissé (drive)", "rangement.py", "if vus[c] > 1 or", "if False and vus[c] > 1 or"),
    ("ranger : seulement dans iCloud = jamais touché", "rangement.py", "            elif dans_le_nuage(st):", "            elif False:"),
    ("ranger : iCloud revérifié avant de déplacer", "rangement.py", "            if self._au_nuage(s):", "            if False:"),
    ("ranger : zones protégées (Google Photos, apps…)", "rangement.py", "PROTEGE = re.compile(", "PROTEGE = re.compile(r\"(?!)\") or re.compile("),
    ("ranger : paquets macOS (photothèque…) laissés", "rangement.py", "            elif nom in sont_dossiers and _ext(nom) and", "            elif False and"),
    ("ranger : fichiers sensibles (.git, .ssh)", "rangement.py", "            if nom in COMPOSANTES_NOIRES or", "            if False and nom in COMPOSANTES_NOIRES or"),
    ("ranger : jamais d'écrasement (Mac)", "rangement.py", "if libc.renamex_np(os.fsencode(src), os.fsencode(dst), 0x4):", "if os.rename(src, dst):"),
    ("ranger : jamais d'écrasement (drive)", "rangement.py", "\"--ignore-existing\", *GARDE, delai=900)", "*GARDE, delai=900)"),
    ("ranger : nom déjà pris = suffixe (2)", "rangement.py", "        while _k(c) in pris:", "        while False:"),
    ("ranger : jamais dans un dossier qui bouge", "rangement.py", "        if any(_k(c) == _k(b) or", "        if False and any(_k(c) == _k(b) or"),
    ("ranger : jamais de copie hors du disque (Mac)", "rangement.py", "            _renommer(s, d)\n", "            __import__(\"shutil\").move(s, d)\n"),
    ("ranger : garde anti-copie (drive)", "rangement.py", "GARDE = [\"--max-transfer\", \"1B\", \"--cutoff-mode\", \"hard\"]", "GARDE = []"),
    ("ranger : déplacement côté serveur exigé (drive)", "rangement.py", "        if not f.get(\"Move\") or (dossiers and not f.get(\"DirMove\")):", "        if False:"),
    ("ranger : journal écrit AVANT le déplacement", "rangement.py",
     "            j.noter({\"avant\": i})\n            ok = lieu.deplacer(src, dst, dossier) or (not lieu.present(src, dossier) and lieu.present(dst, dossier))",
     "            ok = lieu.deplacer(src, dst, dossier) or (not lieu.present(src, dossier) and lieu.present(dst, dossier))\n            j.noter({\"avant\": i})"),
    ("ranger : reprise d'après les faits", "rangement.py", "            ok = lieu.deplacer(src, dst, dossier) or (not lieu.present(src, dossier) and lieu.present(dst, dossier))",
     "            ok = lieu.deplacer(src, dst, dossier)"),
    ("ranger : annuler défait aussi le déplacement coupé", "rangement.py", "sorted((e[\"fait\"] | (e[\"avant\"] - e[\"rate\"])) - e[\"retour\"], reverse=True)",
     "sorted(e[\"fait\"] - e[\"retour\"], reverse=True)"),
    ("ranger : annuler retire les dossiers créés", "rangement.py", "        lieu.retirer_vide(c)", "        pass"),
    ("ranger : journal fermé aux autres", "rangement.py", "        d.chmod(0o700)", "        d.chmod(0o755)"),
    ("ranger : au-delà de MAX, 2e confirmation", "rangement.py", "    if len(moves) > MAX and not confirme:", "    if False:"),
    ("ranger : une confirmation ne sert qu'une fois", "rangement.py", "        srv.plans.pop(cle, None)  # une confirmation", "        None  # une confirmation"),
    ("ranger : catégories déjà là suivies", "rangement.py", "if (k := _cat_existante(c)) and k not in cats:", "if (k := None) and k not in cats:"),
    ("ranger : aucun vrac dans les dossiers du haut", "rangement.py", "    for g, k in gardes.items():  # niveau 2", "    for g, k in {}.items():  # niveau 2"),
    ("ranger : exclure un dossier proposé", "rangement.py", "        plan[\"intentions\"] = [i for i in plan[\"intentions\"] if i[\"src\"] not in touches]", "        pass"),
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
