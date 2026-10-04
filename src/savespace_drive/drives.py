"""Drives en ligne (Google Drive, OneDrive, Dropbox) par rclone (MIT) ; le binaire officiel est inclus dans l'app.
Rien n'est téléchargé : l'analyse lit la liste des fichiers et les empreintes que le SERVICE calcule lui-même
(rclone lsjson --hash-type) et l'espace (rclone about). Ranger = la corbeille du service, jamais un effacement
définitif : un compte dont le type n'a pas de corbeille sûre est refusé avant tout appel. La configuration (jeton de
connexion compris) est écrite par rclone lui-même dans le dossier de l'app (droits 600) ; la sortie de rclone n'est
jamais affichée ni journalisée : seuls son code de retour et le JSON des listes sont lus."""
import collections, configparser, json, os, shutil, subprocess, sys
from pathlib import Path
from savespace_drive import lisible

# clé : (nom affiché, type rclone, empreinte calculée par le service, options qui FORCENT la corbeille, où récupérer)
DRIVES = {
    "gdrive": ("Google Drive", "drive", "md5", ["--drive-use-trash=true"], "https://drive.google.com/drive/trash"),
    "onedrive": ("OneDrive", "onedrive", "quickxor", ["--onedrive-hard-delete=false"], "https://onedrive.live.com/?qt=recyclebin"),
    "dropbox": ("Dropbox", "dropbox", "dropbox", [], "https://www.dropbox.com/deleted_files"),  # rclone n'a pas d'effacement définitif Dropbox
}
REVOQUER = {"gdrive": "https://myaccount.google.com/permissions", "onedrive": "https://account.live.com/consent/Manage",
            "dropbox": "https://www.dropbox.com/account/connected_apps"}  # où retirer l'accès donné à rclone
CONNEXION = {"gdrive": ["scope", "drive"]}  # Drive : accès complet, sinon impossible de mettre à la corbeille
GROS = 10
EN_COURS = []  # rclone lancés et pas finis : tués à la fermeture de l'app (sinon une connexion restée ouverte bloque la suivante)


class Refus(Exception):
    pass


def conf():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "SaveSpace Drive" / "rclone.conf"


def rclone():
    """Le rclone inclus dans l'app d'abord, sinon celui du système (ligne de commande)."""
    inclus = Path(getattr(sys, "_MEIPASS", "/nulle-part")) / ("rclone.exe" if sys.platform == "win32" else "rclone")
    return str(inclus) if inclus.is_file() else shutil.which("rclone")


def _rclone(*args, entree="", delai=3600):
    exe = rclone()
    if not exe:
        raise Refus("Le moteur rclone manque. Il est inclus dans l'app téléchargée ; en ligne de commande, installe rclone.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("RCLONE_")}  # rien du dehors ne change rclone (corbeille comprise)
    p = subprocess.Popen([exe, *args, "--config", str(conf())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    EN_COURS.append(p)
    try:
        sortie, erreurs = p.communicate(entree, timeout=delai)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise Refus("Le service n'a pas répondu à temps. Rien n'a été modifié.") from None
    finally:
        EN_COURS.remove(p)
    return subprocess.CompletedProcess(p.args, p.returncode, sortie, erreurs)


def arreter():
    """Tue les rclone encore en route (connexion abandonnée, app qui se ferme)."""
    for p in list(EN_COURS):
        p.kill()


def type_de(cle):
    c = configparser.ConfigParser(interpolation=None)
    c.read(conf(), encoding="utf-8")
    return c.get(cle, "type", fallback=None)


def etat():
    """Pour la page : chaque drive connecté ou non, et rclone présent ou non."""
    return {"rclone": bool(rclone()), **{k: {"nom": d[0], "ok": type_de(k) == d[1]} for k, d in DRIVES.items()}}


def connecter(cle):
    nom, type_ = DRIVES[cle][:2]
    conf().parent.mkdir(parents=True, exist_ok=True)
    conf().parent.chmod(0o700)  # le jeton n'est lisible que par toi (rclone crée le fichier en 600)
    arreter()  # une connexion précédente restée ouverte tient le port de rclone : on la remplace
    p = _rclone("config", "create", cle, type_, *CONNEXION.get(cle, []), delai=600)  # rclone ouvre le navigateur
    if p.returncode or type_de(cle) != type_:
        raise Refus(f"La connexion à {nom} n'a pas abouti (code {p.returncode}). Rien n'a été modifié. Tu peux réessayer.")
    return {"texte": f"{nom} est connecté. Analyser lit seulement la liste de tes fichiers : rien n'est téléchargé.", "connecte": True}


def deconnecter(cle):
    nom = DRIVES[cle][0]
    if type_de(cle) is not None:
        _rclone("config", "delete", cle, delai=60)  # rclone retire la section (jeton compris) de sa config
    if type_de(cle) is not None:
        raise Refus(f"{nom} n'a pas pu être déconnecté. Rien n'a été modifié.")
    return {"texte": f"{nom} est déconnecté de SaveSpace Drive. Pour retirer aussi l'accès chez {nom}, ouvre sa page "
                     "des applications autorisées et retire « rclone ».", "lien": REVOQUER[cle],
            "lien_texte": f"Retirer l'accès sur le site de {nom}", "deconnecte": True}


def _liste(cle, chemins=None):
    nom, _, h = DRIVES[cle][:3]
    filtre = ["--files-from-raw", "-"] if chemins is not None else []
    p = _rclone("lsjson", "-R", "--files-only", "--hash-type", h, *filtre, f"{cle}:", entree="".join(c + "\n" for c in chemins or ()))
    if p.returncode:
        raise Refus(f"{nom} ne répond pas (code {p.returncode}). Vérifie Internet, ou reconnecte le compte. Rien n'a été modifié.")
    fichiers = [(f["Path"], f.get("Size", -1), (f.get("Hashes") or {}).get(h)) for f in json.loads(p.stdout or "[]")]
    vus = collections.Counter(c for c, _, _ in fichiers)  # même nom au même endroit (Drive le permet) : ambigu, jamais proposé
    return {c: (t, e) for c, t, e in fichiers if vus[c] == 1 and not {"\n", "\r"} & set(c)}  # une ligne = un fichier


def _groupes(fichiers, garder):
    g = collections.defaultdict(list)
    for c, (t, e) in fichiers.items():
        if e and t > 0:  # sans empreinte (Google Docs…) ou vide : jamais comparé
            g[(e, t)].append(c)
    return sorted(({"empreinte": e, "taille": t, "membres": garder(m)} for (e, t), m in g.items() if len(m) >= 2),
                  key=lambda x: (-x["taille"] * (len(x["membres"]) - 1), x["membres"][0]))


def analyser(cle, garder, liste):
    nom, T = DRIVES[cle][0], lisible.taille
    fichiers, p = _liste(cle), _rclone("about", f"{cle}:", "--json", delai=120)
    esp = json.loads(p.stdout or "{}") if not p.returncode else {}
    groupes = _groupes(fichiers, garder)
    rec = sum(g["taille"] * (len(g["membres"]) - 1) for g in groupes)
    gros = sorted(((c, t) for c, (t, _) in fichiers.items() if t > 0), key=lambda x: (-x[1], x[0]))[:GROS]
    utilise = esp.get("used", 0) + esp.get("other", 0)  # « used » compte déjà la corbeille ; « other » = Gmail, Photos
    espace = f"Espace utilisé : {T(utilise)}" + (f" sur {T(esp['total'])}" if esp.get("total") else "") if esp else ""
    return {"texte": f"{nom} : {T(rec)} récupérables en mettant les doublons à la corbeille. {espace}", "resultat": {
        "drive": nom, "total": T(sum(t for t, _ in fichiers.values() if t > 0)), "recuperables": T(rec),
        "recuperables_octets": rec, "groupes": len(groupes), "espace": espace,
        "doublons": [{"taille": T(g["taille"]), "garde": g["membres"][0], "en_trop": g["membres"][1:]} for g in groupes[:liste]],
        "gros": [[c, T(t)] for c, t in gros], "corbeille": T(esp.get("trashed", 0)),
        "autres": T(esp["other"]) if esp.get("other") else "",  # Google Drive : Gmail et Google Photos — rapport seulement
        "caches": 0, "caches_taille": "", "proteges": 0, "nuage": ""}}


def preparer(cle, garder, liste):
    nom = DRIVES[cle][0]
    plan = _groupes(_liste(cle), garder)
    a_jeter = [c for g in plan for c in g["membres"][1:]]
    if not a_jeter:
        return None, {"texte": f"Aucun doublon à mettre à la corbeille sur {nom}.", "confirmer": False}
    total = lisible.taille(sum(g["taille"] * (len(g["membres"]) - 1) for g in plan))
    l = [f"Voici exactement ce qui ira dans la corbeille de {nom} : {lisible.n(len(a_jeter), 'fichier')} en trop ({total}).", ""]
    for g in plan:
        l += [f"on garde : {g['membres'][0]}"] + [f"   → corbeille : {c}" for c in g["membres"][1:]]
    return plan, {"texte": "\n".join(l), "confirmer": True, "nombre": len(a_jeter), "taille": total, "drive": nom,
                  "plan": [{"garde": g["membres"][0], "en_trop": g["membres"][1:]} for g in plan[:liste]], "groupes": len(plan)}


def ranger(cle, plan):
    nom, type_, _, corbeille, _ = DRIVES[cle]
    if type_de(cle) != type_:  # alias, disque local… : pas de corbeille, donc rien n'est effacé
        raise Refus(f"Ce compte {nom} n'a pas de corbeille sûre : rien n'a été supprimé.")
    actuel = _liste(cle, [c for g in plan for c in g["membres"]])  # relu juste avant : le drive a pu changer
    a_jeter = [c for g in plan if actuel.get(g["membres"][0]) == (g["taille"], g["empreinte"])  # l'exemplaire gardé est là
               for c in g["membres"][1:] if actuel.get(c) == (g["taille"], g["empreinte"])]
    if not a_jeter:
        raise Refus(f"{nom} a changé depuis l'aperçu : rien n'a été supprimé. Analyse à nouveau.")
    p = _rclone("delete", f"{cle}:", "--files-from-raw", "-", "--max-delete", str(len(a_jeter)), *corbeille,
                entree="".join(c + "\n" for c in a_jeter))
    if p.returncode:
        raise Refus(f"{nom} a refusé une partie (code {p.returncode}). Ce qui est parti est dans sa corbeille.")
    return (f"C'est fait : {lisible.n(len(a_jeter), 'fichier')} mis dans la corbeille de {nom}.\n"
            f"Tu peux les récupérer depuis cette corbeille pendant 30 jours ; la place est libérée quand elle est vidée.")


def restaurer(cle):
    nom, lien = DRIVES[cle][0], DRIVES[cle][4]
    return {"texte": f"Les fichiers mis à la corbeille se récupèrent depuis la corbeille de {nom}, sur son site : "
                     "sélectionne-les puis « Restaurer ». SaveSpace Drive ne le fait pas à ta place.", "lien": lien,
            "lien_texte": f"Ouvrir la corbeille de {nom}"}


def executer(plans, action, cle, garder, liste):
    if cle not in DRIVES:
        raise Refus("Drive inconnu.")
    if action == "connecter":
        return connecter(cle)
    if action == "restaurer":
        return restaurer(cle)
    if action == "deconnecter":
        plans.pop("drive:" + cle, None)
        return deconnecter(cle)
    if type_de(cle) is None:
        raise Refus(f"Connecte d'abord {DRIVES[cle][0]}.")
    if action == "analyser":
        return analyser(cle, garder, liste)
    if action == "preparer":
        plans["drive:" + cle], rep = preparer(cle, garder, liste)
        return rep
    if action == "ranger":
        if not (plan := plans.pop("drive:" + cle, None)):
            raise Refus("Clique d'abord sur « Mettre les doublons à la corbeille » pour voir la liste exacte.")
        return {"texte": ranger(cle, plan), "fait": True, **{k: v for k, v in restaurer(cle).items() if k != "texte"}}
    raise Refus("Action inconnue.")
