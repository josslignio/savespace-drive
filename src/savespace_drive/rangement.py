"""Ranger un lieu en dossiers et sous-dossiers, comme le propriétaire l'a fait à la main sur Google Drive et pCloud
(docs/RANGEMENT_METHODE.md) : une dizaine de dossiers en haut, numérotés ; aucun fichier en vrac ; les anciens dossiers
déplacés tels quels ; rien d'effacé. Chaque garantie a un test et un mutant (tests/test_rangement.py, tests/mutants.py) :
- PLAN : on lit la LISTE seulement (os.stat sur le Mac ; rclone lsjson pour un drive). Aucun fichier n'est ouvert ni
  téléchargé. Un fichier seulement dans iCloud n'est ni ouvert ni déplacé, ni le dossier qui le contient.
- DÉPLACER : jamais d'écrasement (Mac : renamex_np RENAME_EXCL ; drive : --ignore-existing) ; jamais de copie (Mac :
  renommage sur le même disque ; drive : déplacement côté serveur exigé, et --max-transfer 1B coupe toute copie).
- JOURNAL : chaque déplacement est écrit sur disque (fsync) AVANT d'être fait. « Annuler » le rejoue à l'envers. Une
  coupure au milieu se reprend ou s'annule d'après les faits constatés sur place, pas d'après le journal seul.
- Laissés en place : zones protégées (Google Photos, dossiers d'apps, partagés, sauvegardes), cachés, paquets macOS."""
import collections, ctypes, hashlib, json, os, re, sys, time, unicodedata
from pathlib import Path, PurePosixPath
from savespace_drive import drives, lisible
from savespace_drive.chemins import COMPOSANTES_NOIRES, Garde, RefusChemin, dans_le_nuage
from savespace_drive.drives import Refus

MAX = 500  # au-delà, une 2e confirmation est exigée
GARDE = ["--max-transfer", "1B", "--cutoff-mode", "hard"]  # pas un octet ne transite : côté serveur, ou rien
CATEGORIES = [  # (clé, nom du dossier créé, nom d'un dossier existant qui en tient déjà lieu)
    ("admin", "ADMINISTRATIF", r"administratif|juridique|papiers"),
    ("factures", "FACTURES & ABONNEMENTS", r"factures?|abonnements?"),
    ("documents", "DOCUMENTS", r"documents?|docs"),
    ("photos", "PHOTOS & IMAGES", r"photos?|images?"),
    ("videos", "VIDÉOS", r"videos?|films?"),
    ("musique", "MUSIQUE & AUDIO", r"musiques?|music|audio"),
    ("graphisme", "GRAPHISME", r"graphisme|design"),
    ("logiciels", "LOGICIELS & COMPRESSÉS", r"logiciels?|installateurs?"),
    ("divers", "DIVERS", r"divers|archives?"),
]
TYPES = {"photos": "jpg jpeg png gif heic heif webp bmp tif tiff raw cr2 nef arw dng",
         "videos": "mp4 mov m4v avi mkv wmv webm mts 3gp",
         "musique": "mp3 m4a wav aif aiff flac ogg aac wma",
         "graphisme": "psd ai svg eps sketch fig xd indd afdesign afphoto",
         "documents": "pdf doc docx odt rtf txt md pages xls xlsx ods csv numbers ppt pptx odp key epub",
         "logiciels": "dmg pkg exe msi iso apk zip rar 7z tar gz tgz bz2 xz"}
EXT = {e: k for k, l in TYPES.items() for e in l.split()}
COMPRESSES = set("zip rar 7z tar gz tgz bz2 xz".split())
ADMIN = [("Impôts", r"impots?|taxes?|tax|fiscal|avis d imposition"), ("Banque", r"banque|bank|releves?|rib|iban"),
         ("Santé", r"sante|ordonnances?|mutuelle|medical|medecin|vaccins?"),
         ("Identité", r"passeport|passport|identite|cni|permis|visa|titre de sejour"),
         ("Emploi", r"cv|curriculum|lettre de motivation|cover letter|fiche de paie|bulletin de salaire|payslip"),
         ("Logement", r"bail|loyer|quittances?|etat des lieux|lease"),
         ("Contrats & Assurances", r"contrats?|contracts?|assurances?|insurance|agreement|nda")]
FACTURE = r"factures?|invoices?|recus?|receipts?|abonnements?|subscriptions?|devis"
CAPTURE = r"capture d ecran|captures d ecran|screenshot|screen shot"
PROTEGE = re.compile(r"google photos|computers|ordinateurs|apps|applications|personal vault|coffre fort personnel|crypto folder"
                     r"|pcloud backup|shared with me|partages avec moi|quarantaine|.*\b(sauvegardes?|backups?)\b.*")
PAQUETS = {".app", ".photoslibrary", ".photolibrary", ".musiclibrary", ".tvlibrary", ".imovielibrary", ".fcpbundle",
           ".logicx", ".band", ".bundle", ".framework", ".pkg", ".lrlibrary", ".aplibrary"}
NUMERO = re.compile(r"^\d{1,2}\s*[-–._]\s*")


def _norme(nom):
    s = "".join(c for c in unicodedata.normalize("NFKD", nom) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())  # « Capture d’écran » → « capture d ecran »


def _mot(motif, n):
    return re.search(rf"\b(?:{motif})\b", n) is not None


def _k(c):  # comparaison des noms : sans casse ni forme Unicode (le Mac, OneDrive et Dropbox ne les distinguent pas)
    return unicodedata.normalize("NFC", c).casefold()


def _ext(nom):
    return PurePosixPath(nom).suffix.lower().lstrip(".")


def _sous(k, nom, annee):
    """Le sous-dossier d'un fichier dans la catégorie k : thème pour l'administratif, type pour les logiciels, année sinon."""
    n = _norme(PurePosixPath(nom).stem)
    if k == "admin":
        return next((s for s, m in ADMIN if _mot(m, n)), str(annee or "Sans date"))
    if k == "logiciels":
        return "Fichiers compressés" if _ext(nom) in COMPRESSES else "Installateurs"
    if k == "photos" and _mot(CAPTURE, n):
        return "Captures d'écran"
    return str(annee) if annee else "Sans date"


def _classer(nom, annee):
    n = _norme(PurePosixPath(nom).stem)
    k = "admin" if any(_mot(m, n) for _, m in ADMIN) else "factures" if _mot(FACTURE, n) else EXT.get(_ext(nom), "divers")
    return k, _sous(k, nom, annee)


def _cat_du_nom(nom):
    n = _norme(nom)
    if any(_mot(m, n) for _, m in ADMIN):
        return "admin"
    return next((k for k, _, m in CATEGORIES if _mot(m, n)), None)


def _cat_existante(nom):
    """Un dossier déjà là qui EST une catégorie : « Photos », ou numéroté comme « 04 - PERSO & PHOTOS »."""
    base, numerote = _norme(NUMERO.sub("", nom)), bool(NUMERO.match(nom))
    return next((k for k, _, m in CATEGORIES if (re.search(rf"\b(?:{m})\b", base) if numerote else re.fullmatch(m, base))), None)


def _ancetres(c):
    return [p.as_posix() for p in reversed(PurePosixPath(c).parents)][1:]


# ---- Lire la liste (rien n'est ouvert, rien n'est téléchargé) --------------------------------------------------
def lister_local(racine):
    """{chemin: (dossier ?, taille, année)}, {chemin intouchable: raison}. Seulement os.stat : aucun fichier ouvert."""
    elems, intouchables, garde = {}, {}, Garde([racine])
    for haut, dossiers, fichiers in os.walk(racine):
        rel_haut = Path(haut).relative_to(racine).as_posix()
        garder, sont_dossiers = [], set(dossiers)
        for nom in dossiers + fichiers:
            rel, p = (nom if rel_haut == "." else f"{rel_haut}/{nom}"), os.path.join(haut, nom)
            st = os.stat(p, follow_symlinks=False)
            raison = None
            if nom in COMPOSANTES_NOIRES or nom.endswith(".icloud"):
                raison = "fichier sensible" if nom in COMPOSANTES_NOIRES else "seulement dans iCloud"
            elif nom.startswith("."):
                continue  # caché (.DS_Store…) : jamais proposé, voyage avec son dossier
            elif os.path.islink(p):
                raison = "raccourci"
            elif dans_le_nuage(st):
                raison = "seulement dans iCloud"
            elif nom in sont_dossiers and _ext(nom) and "." + _ext(nom) in PAQUETS:
                raison = "dossier d'app"
            else:
                try:
                    garde.verifier(p)
                except RefusChemin:
                    raison = "fichier sensible"
            if raison:
                intouchables[rel] = raison
            elif nom in sont_dossiers:
                garder.append(nom)
            if not raison or rel_haut == ".":
                elems[rel] = (nom in sont_dossiers, st.st_size, time.localtime(st.st_mtime).tm_year)
        dossiers[:] = garder  # on ne descend ni dans un caché, ni dans un paquet, ni dans un lien
    return elems, intouchables


def lister_drive(cle):
    nom = drives.DRIVES[cle][0]
    p = drives._rclone("lsjson", "-R", "--fast-list", "--no-mimetype", "--drive-skip-shortcuts", f"{cle}:")
    if p.returncode:
        raise Refus(f"{nom} ne répond pas (code {p.returncode}). Vérifie Internet, ou reconnecte le compte. Rien n'a bougé.")
    liste = json.loads(p.stdout or "[]")
    vus = collections.Counter(f["Path"] for f in liste)
    elems, intouchables = {}, {}
    for f in liste:
        c = f["Path"]
        if vus[c] > 1 or {"\n", "\r"} & set(c):
            intouchables[c] = "deux éléments au même nom"
        an = (f.get("ModTime") or "")[:4]
        elems[c] = (bool(f.get("IsDir")), max(f.get("Size") or 0, 0), int(an) if an.isdigit() else 0)
    return elems, intouchables


# ---- Proposer l'arbre ----------------------------------------------------------------------------------------
def proposer(elems, intouchables):
    """Le plan : intentions (src → cible), dossiers existants, laissés en place. Règles : docs/RANGEMENT_METHODE.md."""
    haut = sorted(c for c in elems if "/" not in c)
    bloque = {c.split("/")[0]: r for c, r in sorted(intouchables.items(), key=lambda x: x[0].count("/"), reverse=True)}
    contenu = collections.defaultdict(collections.Counter)  # dossier du haut → types de ses fichiers
    for c, (d, _, _) in elems.items():
        if not d and "/" in c:
            contenu[c.split("/")[0]][EXT.get(_ext(c), "divers")] += 1
    cats, gardes, laisses, intentions = {}, {}, {}, []
    for c in haut:
        if elems[c][0] and c not in intouchables and not PROTEGE.fullmatch(_norme(c)):
            if (k := _cat_existante(c)) and k not in cats:
                cats[k], gardes[c] = c, k
            elif NUMERO.match(c):
                gardes[c] = None  # déjà rangé par son propriétaire : on n'y déplace rien, on range juste son vrac
    for c in haut:
        d = elems[c][0]
        if c in gardes or c.startswith("."):
            continue
        if c in intouchables or PROTEGE.fullmatch(_norme(c)) or (d and c in bloque):
            laisses[c] = intouchables.get(c) or bloque.get(c) or ("sauvegarde" if re.search(r"sauvegarde|backup", _norme(c)) else "zone protégée")
        elif d and not contenu[c]:
            laisses[c] = "dossier vide"
        elif d:
            k = _cat_du_nom(c) or max(sorted(contenu[c]), key=lambda t: contenu[c][t])
            intentions.append({"src": c, "dossier": True, "k": k, "nom": c, "n": sum(contenu[c].values())})
        else:
            k, s = _classer(c, elems[c][2])
            intentions.append({"src": c, "dossier": False, "k": k, "sous": s, "nom": c, "n": 1})
    for g, k in gardes.items():  # niveau 2 : aucun fichier en vrac non plus DANS les dossiers du haut
        for c in sorted(x for x in elems if x.startswith(g + "/") and x.count("/") == 1 and not elems[x][0]):
            nom = c.split("/")[1]
            if c in intouchables or nom.startswith("."):
                continue
            intentions.append({"src": c, "dossier": False, "cible": f"{g}/{_sous(k, nom, elems[c][2])}/{nom}", "n": 1})
    debut = max([int(NUMERO.match(g).group().strip(" -–._")) for g in gardes if NUMERO.match(g)], default=0) + 1
    utilisees = [k for k, _, _ in CATEGORIES if k not in cats and any(i.get("k") == k for i in intentions)]
    noms = {k: cats.get(k) or f"{debut + utilisees.index(k):02d} - {n}" for k, n, _ in CATEGORIES if k in cats or k in utilisees}
    for i in intentions:
        if "cible" not in i:
            i["cible"] = f"{noms[i['k']]}/{i['nom']}" if i["dossier"] else f"{noms[i['k']]}/{i['sous']}/{i['nom']}"
    plan = {"intentions": intentions, "existants": {_k(c): c for c in elems} | {_k(c): c for c in intouchables},
            "fichiers": {_k(c) for c, (d, _, _) in elems.items() if not d}, "laisses": laisses,
            "haut_avant": [c for c in haut if not c.startswith(".")]}
    _attribuer(plan)
    return plan


def _suffixe(c, n, dossier):
    p = PurePosixPath(c)
    return str(p.with_name(f"{p.name} ({n})" if dossier or not p.suffix else f"{p.stem} ({n}){p.suffix}"))


def _attribuer(plan):
    """Cibles définitives : jamais un nom déjà pris (suffixe « (2) »), jamais dans un dossier qui bouge lui-même."""
    pris, blocs, moves, conflits = set(plan["existants"]), [i["src"] for i in plan["intentions"] if i["dossier"]], [], {}
    for i in sorted(plan["intentions"], key=lambda i: (i["dossier"], i["src"])):  # fichiers d'abord, puis dossiers
        c, n = i["cible"], 1
        if any(_k(c) == _k(b) or _k(c).startswith(_k(b) + "/") for b in blocs) or any(_k(a) in plan["fichiers"] for a in _ancetres(c)):
            conflits[i["src"]] = "conflit de nom"
            continue
        while _k(c) in pris:
            n += 1
            c = _suffixe(i["cible"], n, i["dossier"])
        pris.update(_k(a) for a in _ancetres(c) + [c])
        moves.append([i["src"], c, i["dossier"], i["n"]])
    plan["moves"], plan["conflits"] = moves, conflits


def modifier(plan, op, chemin, nom=""):
    """Renommer, fusionner dans un autre dossier proposé, ou exclure un dossier proposé (et tout ce qu'il contient)."""
    dedans = lambda c: _k(c) == _k(chemin) or _k(c).startswith(_k(chemin) + "/")
    touches = {m[0]: m[1] for m in plan["moves"] if dedans(m[1])}  # src → cible actuelle, sous ce dossier
    if not chemin or not touches:
        raise Refus("Ce dossier n'est plus dans la proposition.")
    if op == "exclure":
        plan["intentions"] = [i for i in plan["intentions"] if i["src"] not in touches]
    elif op in ("renommer", "fusionner"):
        if _k(chemin) in plan["existants"]:
            raise Refus("Ce dossier existe déjà : on ne le renomme pas d'ici. Tu peux l'exclure.")
        if op == "renommer":
            nom = " ".join((nom or "").split())
            if not nom or nom.startswith(".") or len(nom) > 100 or re.search(r'[/\\:*?"<>|\x00-\x1f]', nom):
                raise Refus("Choisis un nom simple, sans / \\ : * ? \" < > |.")
            nouveau = str(PurePosixPath(chemin).with_name(nom))
        else:
            dossiers = {a for m in plan["moves"] for a in _ancetres(m[1])}
            if nom not in dossiers or dedans(nom):
                raise Refus("Choisis un autre dossier de la proposition.")
            nouveau = nom
        for i in plan["intentions"]:
            if i["src"] in touches:
                i["cible"] = nouveau + touches[i["src"]][len(chemin):]
    else:
        raise Refus("Modification inconnue.")
    _attribuer(plan)


def apercu(plan, lieu):
    moves, T = plan["moves"], collections.defaultdict(lambda: [0, {}])
    for src, dst, d, n in moves:
        haut, sous = dst.split("/")[:2]
        T[haut][0] += n
        T[haut][1][sous] = T[haut][1].get(sous, 0) + n
    ex = lambda c: _k(c) in plan["existants"]
    arbre = [{"chemin": h, "n": n, "existe": ex(h), "sous": [{"chemin": f"{h}/{s}", "nom": s, "n": k, "existe": ex(f"{h}/{s}")}
                                                         for s, k in sorted(subs.items())]} for h, (n, subs) in sorted(T.items())]
    bouges = {m[0] for m in moves}
    reste = [c for c in plan["haut_avant"] if c not in bouges]  # ce qui restera en haut, à côté des dossiers proposés
    laisses = sorted({**plan["laisses"], **plan["conflits"]}.items())
    return {"lieu": lieu, "nombre": len(moves), "fichiers": sum(m[3] for m in moves), "max": MAX, "arbre": arbre,
            "dossiers_haut": len(set(T) | {c for c in reste if _k(c) not in plan["fichiers"]}),
            "vrac": sum(_k(c) in plan["fichiers"] for c in reste), "exemples": [[m[0], m[1]] for m in moves[:30]],
            "laisses": [[c, r] for c, r in laisses[:50]], "total_laisses": len(laisses)}


# ---- Les deux lieux : le Mac (renommage) et un drive (déplacement côté serveur) -------------------------------
def _renommer(src, dst):
    """Renommage sur le même disque, refusé si la destination existe (fichier OU dossier, même vide). Jamais une copie."""
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renamex_np(os.fsencode(src), os.fsencode(dst), 0x4):  # RENAME_EXCL
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e), dst)
    elif os.name == "nt":
        os.rename(src, dst)  # Windows refuse d'écraser
    else:
        if os.path.lexists(dst):
            raise FileExistsError(dst)
        os.rename(src, dst)


class Local:
    def __init__(self, racine):
        self.racine, self.cle, self.nom, self.garde = racine, f"local:{racine}", racine.name, Garde([racine])

    def _p(self, rel):
        return self.racine.joinpath(*rel.split("/"))

    def lister(self):
        return lister_local(self.racine)

    def verifier(self, dossiers):
        pass

    def present(self, rel, dossier=False):
        return os.path.lexists(self._p(rel))

    def _au_nuage(self, p):
        if dans_le_nuage(os.stat(p, follow_symlinks=False)):
            return True
        return p.is_dir() and any(dans_le_nuage(os.stat(os.path.join(h, n), follow_symlinks=False)) or n.endswith(".icloud")
                                  for h, ds, fs in os.walk(p) for n in ds + fs)

    def deplacer(self, src, dst, dossier):
        s, d = self._p(src), self._p(dst)
        try:
            self.garde.verifier(s)
            self.garde.verifier(d)
            if self._au_nuage(s):  # renvoyé au nuage depuis l'aperçu : on n'y touche pas
                return False
            d.parent.mkdir(parents=True, exist_ok=True)
            _renommer(s, d)
            return True
        except (OSError, RefusChemin):
            return False

    def retirer_vide(self, rel):
        try:
            os.rmdir(self._p(rel))  # refuse un dossier qui n'est pas vide
        except OSError:
            pass


class Drive:
    def __init__(self, cle):
        self.cle, self.nom = cle, drives.DRIVES[cle][0]

    def lister(self):
        return lister_drive(self.cle)

    def verifier(self, dossiers):
        p = drives._rclone("backend", "features", f"{self.cle}:", delai=120)
        f = json.loads(p.stdout or "{}").get("Features", {}) if not p.returncode else {}
        if not f.get("Move") or (dossiers and not f.get("DirMove")):
            raise Refus(f"{self.nom} ne sait pas déplacer sans télécharger : rien n'a bougé.")

    def present(self, rel, dossier=False):
        if dossier:  # un dossier « présent » = il y reste au moins un fichier
            p = drives._rclone("lsjson", "-R", "--files-only", "--no-mimetype", f"{self.cle}:{rel}", delai=600)
            return not p.returncode and json.loads(p.stdout or "[]") != []
        return not drives._rclone("lsjson", "--stat", "--no-mimetype", f"{self.cle}:{rel}", delai=120).returncode

    def deplacer(self, src, dst, dossier):
        p = drives._rclone("moveto", f"{self.cle}:{src}", f"{self.cle}:{dst}", "--ignore-existing", *GARDE, delai=900)
        return not p.returncode and not self.present(src, dossier)  # vérifié : la source n'est plus là

    def retirer_vide(self, rel):
        drives._rclone("rmdir", f"{self.cle}:{rel}", delai=120)  # rclone rmdir refuse un dossier qui n'est pas vide


# ---- Journal : écrit AVANT chaque déplacement, rejoué à l'envers pour annuler ---------------------------------
class Journal:
    def __init__(self, cle):
        d = drives.conf().parent / "rangements"
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)
        self.chemin = d / (hashlib.sha256(cle.encode()).hexdigest()[:16] + ".jsonl")

    def noter(self, o):
        with open(self.chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def etat(self):
        lignes = []
        if self.chemin.exists():
            for l in self.chemin.read_text(encoding="utf-8").splitlines():
                try:
                    lignes.append(json.loads(l))
                except ValueError:
                    break  # dernière ligne coupée par un arrêt : rien après n'a commencé
        if not lignes:
            return None
        e = {"moves": lignes[0]["moves"], "crees": lignes[0]["crees"], "fait": set(), "avant": set(), "rate": set(),
             "retour": set(), "annulation": False, "fin": None}
        for o in lignes[1:]:
            for k in ("fait", "avant", "rate", "retour"):
                if k in o:
                    e[k].add(o[k])
            e["annulation"] |= "annulation" in o
            e["fin"] = o.get("fin", e["fin"])
        e["phase"] = {"rangé": "fait", "annulé": None}.get(e["fin"], "annulation" if e["annulation"] else "interrompu")
        return e


def etat(lieu):
    e = Journal(lieu.cle).etat()
    return e if e and e["phase"] else None


def ranger(lieu, plan, confirme, progres):
    moves = [m[:3] for m in plan["moves"]]
    if not moves:
        raise Refus("Rien à ranger ici.")
    if len(moves) > MAX and not confirme:
        raise Refus(f"C'est beaucoup : {len(moves)} déplacements d'un coup. Confirme une 2e fois.")
    if (e := etat(lieu)) and e["phase"] != "fait":
        raise Refus("Le rangement précédent s'est arrêté au milieu : reprends-le ou annule-le d'abord.")
    lieu.verifier(any(m[2] for m in moves))
    j = Journal(lieu.cle)
    if j.chemin.exists():  # l'ancien rangement fini est gardé à côté ; seul le dernier s'annule depuis l'app
        j.chemin.rename(j.chemin.with_name(f"{j.chemin.stem}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"))
    crees = sorted({a for m in moves for a in _ancetres(m[1]) if _k(a) not in plan["existants"]}, key=lambda a: (-a.count("/"), a))
    j.noter({"v": 1, "lieu": lieu.cle, "debut": time.strftime("%Y-%m-%d %H:%M:%S"), "moves": moves, "crees": crees})
    return _avancer(lieu, j, set(), progres)


def _avancer(lieu, j, faits, progres):
    moves, rates = j.etat()["moves"], []
    for i, (src, dst, dossier) in enumerate(moves):
        if i not in faits:
            j.noter({"avant": i})
            ok = lieu.deplacer(src, dst, dossier) or (not lieu.present(src, dossier) and lieu.present(dst, dossier))
            j.noter({"fait": i} if ok else {"rate": i})
            if not ok:
                rates.append(src)
        progres(i + 1, len(moves))
    j.noter({"fin": "rangé"})
    tops = {m[1].split("/")[0] for m in moves}
    ok = len(moves) - len(rates)
    texte = f"C'est fait : {lisible.n(ok, 'élément')} rangé{'s' if ok > 1 else ''} dans {lisible.n(len(tops), 'dossier')}."
    if rates:
        texte += (f"\n{lisible.n(len(rates), 'élément')} n'a pas pu bouger (changé depuis l'aperçu) : resté à sa place, "
                  "par exemple « " + rates[0] + " ».")
    return texte + "\n« Annuler ce rangement » remet tout comme avant."


def reprendre(lieu, progres):
    e = etat(lieu)
    if not e or e["phase"] != "interrompu":
        raise Refus("Aucun rangement à reprendre ici.")
    return _avancer(lieu, Journal(lieu.cle), e["fait"], progres)


def annuler(lieu, progres):
    j, e = Journal(lieu.cle), etat(lieu)
    if not e:
        raise Refus("Aucun rangement à annuler ici.")
    j.noter({"annulation": time.strftime("%Y-%m-%d %H:%M:%S")})
    a_defaire = sorted((e["fait"] | (e["avant"] - e["rate"])) - e["retour"], reverse=True)  # à l'envers
    revenus, restes = 0, []
    for k, i in enumerate(a_defaire):
        src, dst, dossier = e["moves"][i]
        if lieu.deplacer(dst, src, dossier):
            revenus += 1
            j.noter({"retour": i})
        elif lieu.present(src, dossier) and not lieu.present(dst, dossier):  # jamais parti (coupure avant le déplacement)
            j.noter({"retour": i})
        else:
            restes.append(dst)
        progres(k + 1, len(a_defaire))
    for c in e["crees"]:  # les dossiers créés par le rangement, s'ils sont vides (les plus profonds d'abord)
        lieu.retirer_vide(c)
    j.noter({"fin": "annulé"})
    texte = f"Tout est revenu à sa place : {lisible.n(revenus, 'élément')}."
    if restes:
        texte += f"\n{lisible.n(len(restes), 'élément')} n'a pas pu revenir (un autre fichier a pris sa place), par exemple « {restes[0]} »."
    return texte


# ---- Appelé par l'écran (app.py) ------------------------------------------------------------------------------
def executer(srv, action, d, dossier_valide):
    if d.get("drive"):
        cle = d["drive"]
        if cle not in drives.DRIVES:
            raise Refus("Drive inconnu.")
        if drives.type_de(cle) is None:
            raise Refus(f"Connecte d'abord {drives.DRIVES[cle][0]}.")
        lieu = Drive(cle)
    else:
        lieu = Local(dossier_valide(d.get("dossier")))
    cle, progres = "rangement:" + lieu.cle, lambda fait, total: setattr(srv, "progres", {"fait": fait, "total": total})
    if action == "rangement_plan":
        if (e := etat(lieu)) and e["phase"] != "fait":
            return {"interrompu": {"phase": e["phase"], "faits": len(e["fait"]), "total": len(e["moves"])}}
        srv.plans[cle] = plan = proposer(*lieu.lister())
        return {"apercu": apercu(plan, lieu.nom), "annulable": bool(e)}
    if action == "rangement_modifier":
        if not (plan := srv.plans.get(cle)):
            raise Refus("Clique d'abord sur « Ranger en dossiers » pour voir la proposition.")
        modifier(plan, d.get("op"), d.get("chemin") or "", d.get("nom") or "")
        return {"apercu": apercu(plan, lieu.nom), "annulable": bool(etat(lieu))}
    if action == "rangement_go":
        if not (plan := srv.plans.get(cle)):
            raise Refus("Clique d'abord sur « Ranger en dossiers » pour voir la proposition.")
        texte = ranger(lieu, plan, bool(d.get("confirme_gros")), progres)
        srv.plans.pop(cle, None)  # une confirmation ne sert qu'une fois
        return {"texte": texte, "fait": True}
    if action == "rangement_reprendre":
        return {"texte": reprendre(lieu, progres), "fait": True}
    if action == "rangement_annuler":
        srv.plans.pop(cle, None)
        return {"texte": annuler(lieu, progres), "restaure": True}
    raise Refus("Action inconnue.")
