"""Sortie lisible (APP0) : traduit en phrases simples ce que les commandes impriment.
Aucune commande n'est modifiée : `--json` (ou une sortie redirigée) rend les octets d'origine."""
import json, os, re, sys
from pathlib import PurePosixPath

TYPES = {"videos": "Vidéos", "archives": "Archives", "installeurs": "Installeurs",
         "sauvegardes": "Sauvegardes", "autres": "Autres fichiers"}


def taille(o):
    """Octets -> « 8,5 Mo » (unités de 1000, comme le Finder), virgule française."""
    if o < 1000:
        return f"{o} octet" + ("s" if o > 1 else "")
    for unite in ("Ko", "Mo", "Go", "To"):
        o /= 1000
        if o < 999.95 or unite == "To":
            return f"{o:.1f}".replace(".", ",") + " " + unite


def n(k, mot):
    return f"{k} {mot}" + ("s" if k > 1 else "")


def court(chemin):
    """Chemin relatif raccourci : premier dossier/…/deux derniers éléments."""
    p = PurePosixPath(chemin).parts
    return "/".join(p[:1] + ("…",) + p[-2:]) if len(p) > 4 else chemin


def analyse(r, limite=20):
    groupes = [g for g in r["doublons"] if g["taille"] > 0]
    l = [f"Taille totale du dossier : {taille(r['total_octets'])}.", ""]
    if groupes:
        l.append(f"Tu peux récupérer {taille(r['recuperables_octets'])} : "
                 f"{n(len(groupes), 'groupe')} de fichiers identiques (doublons).")
        for i, g in enumerate(groupes[:limite], 1):
            l.append(f"  Groupe {i} — {len(g['chemins'])} copies identiques de {taille(g['taille'])} :")
            l.append(f"    on garde : {court(g['chemins'][0])}")
            l += [f"    en trop  : {court(c)}" for c in g["chemins"][1:]]
        if len(groupes) > limite:
            l.append(f"  … et {len(groupes) - limite} autres groupes.")
    else:
        l.append("Aucun doublon trouvé.")
    if r["gros"]:
        l += ["", "Les plus gros fichiers :"] + [f"  {taille(g['taille']):>10}  {court(g['chemin'])}" for g in r["gros"]]
    if r["caches"]:
        l += ["", f"{n(len(r['caches']), 'fichier')} de cache ou de journal repérés."]
    if (nu := r.get("nuage_seulement", {})).get("fichiers"):
        l += ["", f"{n(nu['fichiers'], 'fichier')} dans le nuage seulement ({taille(nu['octets'])}) : pas téléchargés, donc pas examinés."]
    if r["proteges"]:
        l += ["", f"{n(len(r['proteges']), 'fichier')} sensibles (clés, .git) ignorés : on n'y touche jamais."]
    return "\n".join(l + ["", "Rien n'a été modifié : c'est seulement une analyse."])


def _doublons(d, argv):
    if not d["groupes"]:
        return "Aucun doublon trouvé. Rien n'a été déplacé."
    l = [f"{n(len(d['groupes']), 'groupe')} de fichiers identiques :"]
    for i, g in enumerate(d["groupes"], 1):
        l.append(f"  Groupe {i} : on garde {court(g['conserve'])}")
        l += [f"    en trop : {court(c)}" for c in g["membres"] if c != g["conserve"]]
    if d["vides"]:
        l.append(f"{n(d['vides'], 'fichier')} vides ignorés.")
    return "\n".join(l + ["Rien n'a été déplacé : c'est seulement une liste."])


def _gros(d, argv):
    l = ["Les plus gros fichiers, par type :"]
    for t in sorted(d["groupes"]):
        l += [f"  {TYPES.get(t, t)} :"] + [f"    {taille(e['taille']):>10}  {court(e['chemin'])}" for e in d["groupes"][t]]
    return "\n".join(l if d["groupes"] else ["Aucun fichier trouvé ici."])


def _similaires(d, argv):
    if not d["groupes"]:
        return "Aucune image ou vidéo presque identique trouvée."
    return "\n".join([f"{n(len(d['groupes']), 'groupe')} d'images ou vidéos presque identiques :"]
                     + [f"  Groupe {i} : " + ", ".join(map(court, g)) for i, g in enumerate(d["groupes"], 1)]
                     + ["Rien n'a été modifié."])


def _doctor(d, argv):
    l = ["Outils d'aide (facultatifs : l'analyse et les doublons marchent sans eux) :"]
    for nom, f in sorted(d["outils"].items()):
        if nom == "osxphotos" and sys.platform != "darwin":
            continue  # Photos n'existe que sur Mac
        aide = f"pour l'installer : {f['installer']}" if sys.platform == "darwin" else "à télécharger sur le site de l'outil"
        l.append(f"  {nom} : " + ("présent" if f["present"] else f"absent — {aide}"))
    return "\n".join(l)


def _range(d, argv):
    fait = "--oui" in argv
    if not d["deplacements"]:
        return "Rien à ranger."
    return (f"{n(d['deplacements'], 'fichier')} ({taille(d['octets'])}) "
            + ("rangés" if fait else "seraient rangés") + " dans : " + ", ".join(d["dossiers"]) + ".")


RENDUS = {"analyse": lambda d, a: analyse(d), "doublons": _doublons, "gros": _gros,
          "similaires": _similaires, "doctor": _doctor, "range": _range}
CONFIRMER = "Tu confirmes ? Tape o puis Entrée (toute autre réponse annule, rien ne bouge) : "
LIGNES = {
    "caches": [(r"cibles=(\d+) octets=(\d+)", lambda m, a: f"{n(int(m[1]), 'fichier')} (caches, journaux, vieux téléchargements, installeurs) iraient à la corbeille : {taille(int(m[2]))}."),
               (r"o/N : ", lambda m, a: CONFIRMER),
               (r"deplaces=(\d+) : .*", lambda m, a: f"{n(int(m[1]), 'fichier')} mis à la corbeille. La place n'est libérée qu'en vidant la corbeille ; sur iCloud Drive, la suppression vaut aussi sur tes autres appareils.")],
    "decharge": [(r"fichiers_a_deplacer=(\d+) octets=(\d+)", lambda m, a: f"{n(int(m[1]), 'gros fichier')} à déplacer ({taille(int(m[2]))}). Chaque copie est vérifiée avant d'effacer l'original."),
                 (r"o/N : ", lambda m, a: CONFIRMER),
                 (r"decharge : (\d+) fichier\(s\) traité\(s\)", lambda m, a: f"C'est fait : {n(int(m[1]), 'fichier')} déplacés et vérifiés.")],
    "range": [(r"(.+) -> (.+)", lambda m, a: f"  {os.path.basename(m[1])}  →  {os.path.basename(os.path.dirname(m[2]))}/"),
              (r"o/N : ", lambda m, a: None if "--oui" in a else "C'est un aperçu : rien n'a bougé. Pour ranger pour de vrai, relance avec --oui.")],
    "tout": [(r"(\w+) \? \(o/N\)", lambda m, a: f"Étape « {m[1]} » ? Tape o puis Entrée (sinon elle est sautée) :"),
             (r"(\w+) : faite", lambda m, a: f"{m[1]} : fait."),
             (r"(\w+) : refusée", lambda m, a: f"{m[1]} : sautée."),
             (r"(\w+) : déjà journalisée, sautée", lambda m, a: f"{m[1]} : déjà fait, sauté."),
             (r"(\w+) : absente à HEAD, ignorée", lambda m, a: f"{m[1]} : pas disponible dans cette version."),
             (r"La quarantaine reste .*", lambda m, a: "Les fichiers mis de côté restent sur le même disque : la place n'est libérée qu'une fois ce dossier vidé.")],
}


def traduire(nom, argv, ligne):
    """Une ligne imprimée par la commande -> sa version lisible (None = ligne déjà dite ailleurs)."""
    if ligne.startswith("{") and nom in RENDUS:
        try:
            return RENDUS[nom](json.loads(ligne), argv)
        except (ValueError, KeyError, TypeError):
            return ligne
    if nom in ("gros", "similaires"):
        return None  # le résumé final (JSON) redit tout, en mieux
    for motif, rendu in LIGNES.get(nom, ()):
        if m := re.fullmatch(motif, ligne):
            return rendu(m, argv)
    return ligne


class Traducteur:
    """Remplace sys.stdout le temps d'une commande ; traduit ligne par ligne (et l'invite o/N au flush)."""
    def __init__(self, nom, argv, sortie):
        self.nom, self.argv, self.sortie, self.reste = nom, argv, sortie, ""

    def _emettre(self, ligne, fin):
        t = traduire(self.nom, self.argv, ligne)
        if t is not None:
            self.sortie.write(t + fin)

    def write(self, s):
        self.reste += s
        while "\n" in self.reste:
            ligne, self.reste = self.reste.split("\n", 1)
            self._emettre(ligne, "\n")
        return len(s)

    def flush(self):
        if self.reste:
            self._emettre(self.reste, "")
            self.reste = ""
        self.sortie.flush()


def lisible(nom, reste, deleguer):
    vrai, sys.stdout = sys.stdout, Traducteur(nom, reste, sys.stdout)
    try:
        rc = deleguer(nom, reste)
    finally:
        sys.stdout.flush()
        sys.stdout = vrai
    if nom == "restaure" and rc == 0:
        print("C'est fait : les fichiers mis de côté sont revenus à leur place.")
    return rc
