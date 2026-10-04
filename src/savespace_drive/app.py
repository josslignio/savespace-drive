"""Écran local (APP1) : une page servie sur 127.0.0.1 seulement ; rien ne sort de la machine.
La même page s'affiche dans le navigateur (`savespace-drive app`) ou dans la fenêtre native (bureau.py, APP2).
Aucune logique de nettoyage ici : Analyser = analyse.analyser (à blanc) ; Ranger = doublons.detecter puis
quarantaine.mettre_en_quarantaine (manifeste, réversible) ; Annuler = quarantaine.restaure.
Où chercher : un dossier de l'ordinateur, iCloud Drive (dossier local : les fichiers pas téléchargés ne sont jamais
ouverts), ou un drive en ligne (drives.py : liste et empreintes du service, corbeille du service)."""
import contextlib, html, io, json, os, re, secrets, socketserver, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from savespace_drive import analyse, doctor, doublons, drives, lisible, quarantaine
from savespace_drive.chemins import Garde, dans_le_nuage

QUARANTAINE = "quarantaine"  # dossier « mis de côté », à l'intérieur du dossier choisi
VERROU = threading.Lock()  # une action à la fois (elles changent le dossier courant du processus) : garde le démarrage
ATTENTE = 20  # s : une action plus longue répond « en cours » et la page redemande (« suivre ») — pas de requête de 5 min
LISTE = 200  # éléments détaillés au plus par liste affichée (les totaux, eux, comptent tout)
RACCOURCIS = (("Téléchargements", "Downloads"), ("Bureau", "Desktop"), ("Documents", "Documents"), ("Vidéos", "Videos"))
MAC_SEULEMENT = {"osxphotos"}  # Photos n'existe que sur Mac : outil caché ailleurs
COPIE = re.compile(r"\bcopie\b|\bcopy\b|\(\d+\)|[ _][1-9]$", re.I)  # Copie de X, X - copie, Copy of X, X copy, X (1), X_1, X 1


class Refus(Exception):
    pass


def raccourcis():
    d_ = {"Videos": "Movies"} if sys.platform == "darwin" else {}  # Vidéos s'appelle Movies sur Mac
    return [(nom, str(Path.home() / d_.get(d, d))) for nom, d in RACCOURCIS if (Path.home() / d_.get(d, d)).is_dir()]


def icloud():
    """Le dossier iCloud Drive s'il existe sur cet ordinateur (Mac, ou iCloud pour Windows), sinon None."""
    d = Path.home() / ("Library/Mobile Documents/com~apple~CloudDocs" if sys.platform == "darwin" else "iCloudDrive")
    return str(d) if d.is_dir() else None


def _au_nuage(p):
    try:
        return dans_le_nuage(os.stat(p))
    except OSError:
        return False


def outils():
    """Outils en plus (facultatifs) visibles sur ce système : (nom, présent). L'analyse et les doublons marchent sans."""
    return [(nom, f["present"]) for nom, f in sorted(doctor.examiner()["outils"].items())
            if sys.platform == "darwin" or nom not in MAC_SEULEMENT]


def dossier_valide(brut):
    brut = (brut or "").strip()
    if not brut:
        raise Refus("Choisis d'abord un dossier.")
    r = Path(os.path.realpath(os.path.expanduser(brut)))
    maisons = {os.path.realpath(Path.home())} | ({os.path.realpath(os.environ["HOME"])} if os.environ.get("HOME") else set())
    if r.parent == r or str(r) in maisons:
        raise Refus("Ce dossier est trop large : choisis un dossier précis, par exemple Téléchargements.")
    if not r.is_dir():
        raise Refus(f"Dossier introuvable : {brut}")
    return r


def _hors_q(chemins):
    return [c for c in chemins if c.split("/")[0] != QUARANTAINE]


def _original_d_abord(chemins):
    """Dans un groupe de doublons, celui qu'on garde en premier : pas un nom de copie, puis le moins profond,
    le nom le plus court, l'ordre alphabétique. (Les commandes en ligne gardent leur règle : le 1er alphabétique.)"""
    return sorted(chemins, key=lambda c: (bool(COPIE.search(PurePosixPath(c).stem)), c.count("/"), len(PurePosixPath(c).name), c))


@contextlib.contextmanager
def _dans(dossier):
    avant, erreurs = os.getcwd(), io.StringIO()
    os.chdir(dossier)
    try:
        with contextlib.redirect_stderr(erreurs):
            yield erreurs
    finally:
        os.chdir(avant)


def _taille(chemin):
    try:
        return os.path.getsize(chemin)
    except OSError:
        return 0


def analyser(dossier):
    r = analyse.analyser(dossier, 10)
    r["doublons"] = [dict(g, chemins=_original_d_abord(c)) for g in r["doublons"] if len(c := _hors_q(g["chemins"])) >= 2]
    r["recuperables_octets"] = sum(g["taille"] * (len(g["chemins"]) - 1) for g in r["doublons"])
    r["gros"] = [g for g in r["gros"] if _hors_q([g["chemin"]])]
    groupes = sorted((g for g in r["doublons"] if g["taille"]), key=lambda g: -g["taille"] * (len(g["chemins"]) - 1))
    caches = sum(_taille(dossier / c) for c in r["caches"])
    T = lisible.taille
    return {"texte": lisible.analyse(r), "resultat": {
        "total": T(r["total_octets"]), "recuperables": T(r["recuperables_octets"]),
        "recuperables_octets": r["recuperables_octets"], "groupes": len(groupes),
        "doublons": [{"taille": T(g["taille"]), "garde": g["chemins"][0], "en_trop": g["chemins"][1:]} for g in groupes[:LISTE]],
        "gros": [[g["chemin"], T(g["taille"])] for g in r["gros"]],
        "caches": len(r["caches"]), "caches_taille": T(caches), "proteges": len(r["proteges"]),
        "nuage": lisible.nuage(r["nuage_seulement"]["fichiers"], r["nuage_seulement"]["octets"]) if r["nuage_seulement"]["fichiers"] else ""}}


def preparer(dossier):
    plan = []
    for g in doublons.detecter(dossier, Garde([dossier])):
        if len(m := _original_d_abord(_hors_q(g["membres"]))) >= 2:
            plan.append({"empreinte": g["empreinte"], "membres": m, "conserve": m[0]})
    a_deplacer = [c for g in plan for c in g["membres"][1:]]
    if not a_deplacer:
        return {"groupes": []}, {"texte": "Aucun doublon à ranger dans ce dossier.", "confirmer": False}
    total = sum(os.path.getsize(dossier / c) for c in a_deplacer)
    l = [f"Voici exactement ce qui va bouger : {lisible.n(len(a_deplacer), 'fichier')} en trop ({lisible.taille(total)})",
         f"iront dans le dossier « {QUARANTAINE} », à l'intérieur de ce dossier. Rien n'est effacé.", ""]
    for g in plan:
        l += [f"on garde : {g['conserve']}"] + [f"   → mis de côté : {c}" for c in g["membres"][1:]]
    texte = "\n".join(l + ["", "Clique sur « Oui, ranger » pour le faire. « Annuler / restaurer » remet tout en place."])
    return {"groupes": plan}, {"texte": texte, "confirmer": True, "nombre": len(a_deplacer), "taille": lisible.taille(total), "quarantaine": QUARANTAINE,
                               "plan": [{"garde": g["conserve"], "en_trop": g["membres"][1:]} for g in plan[:LISTE]],
                               "groupes": len(plan)}


def ranger(dossier, plan):
    if any(_au_nuage(dossier / c) for g in plan["groupes"] for c in g["membres"]):  # renvoyé au nuage depuis l'aperçu
        raise Refus("Un fichier n'est plus téléchargé sur cet ordinateur depuis l'aperçu : rien n'a bougé. Analyse à nouveau.")
    with _dans(dossier) as erreurs:
        rc, deplaces, _ = quarantaine.mettre_en_quarantaine(plan, Garde([dossier]), QUARANTAINE)
    if rc:
        raise Refus("Arrêt : " + erreurs.getvalue().strip() + "\nCe qui a déjà été mis de côté revient avec « Annuler / restaurer ».")
    return (f"C'est fait : {lisible.n(deplaces, 'fichier')} mis de côté dans « {QUARANTAINE} ».\n"
            "La place n'est vraiment libérée que quand tu supprimes ce dossier toi-même, une fois sûr de toi.")


def restaurer(dossier):
    manifestes = sorted((dossier / QUARANTAINE).glob("*/manifeste.json"))
    entrees = [e for m in manifestes for e in json.loads(m.read_text(encoding="utf-8"))["entrees"]]
    a_remettre = sum((dossier / e["quarantaine"]).is_file() for e in entrees)
    if not a_remettre:
        raise Refus("Rien à restaurer : aucun fichier n'est mis de côté dans ce dossier.")
    with _dans(dossier) as erreurs:
        rcs = [quarantaine.restaure(str(m.relative_to(dossier))) for m in manifestes]
    if any(rcs):
        raise Refus("Restauration impossible : " + erreurs.getvalue().strip())
    return f"C'est fait : {lisible.n(a_remettre, 'fichier')} remis à leur place d'origine."


class Ecran(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _repondre(self, code, type_, corps):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _autorise(self, jeton):  # Host contrôlé (anti-rebinding) + jeton aléatoire (anti-requête d'un autre site)
        return self.headers.get("Host") == self.server.hote and jeton == self.server.jeton

    def do_GET(self):
        if not self._autorise(self.path.removeprefix("/?t=")):
            return self._repondre(403, "text/plain; charset=utf-8", "Accès refusé.".encode())
        self._repondre(200, "text/html; charset=utf-8", page(self.server.jeton).encode())

    def do_POST(self):
        if not self._autorise(self.headers.get("X-Jeton")):
            return self._repondre(403, "text/plain; charset=utf-8", "Accès refusé.".encode())
        srv, action = self.server, self.path.strip("/")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            d = {}
        if action == "quitter":  # toujours possible, même pendant une action
            srv.fini, rep = True, {"texte": "SaveSpace Drive est fermé. Tu peux fermer cet onglet."}
        else:
            with VERROU:
                if action != "suivre" and not (srv.fil and srv.fil.is_alive()):
                    srv.rep, srv.fil = None, threading.Thread(target=lambda: setattr(srv, "rep", executer(srv, action, d)), daemon=True)
                    srv.fil.start()
                elif action != "suivre":
                    return self._json({"texte": "Une action est déjà en cours : attends qu'elle se termine.", "erreur": True})
            if srv.fil:
                srv.fil.join(ATTENTE)
            rep = {"en_cours": True} if srv.fil and srv.fil.is_alive() else (srv.rep or {"texte": "Rien en cours.", "erreur": True})
        self._json(rep)

    def _json(self, rep):
        self._repondre(200, "application/json; charset=utf-8", json.dumps(rep, ensure_ascii=False).encode())


def executer(srv, action, d):
    try:
        if d.get("drive"):
            return drives.executer(srv.plans, action, d["drive"], _original_d_abord, LISTE)
        dossier = dossier_valide(d.get("dossier"))
        if action == "analyser":
            return analyser(dossier)
        if action == "preparer":
            srv.plans[str(dossier)], rep = preparer(dossier)
            return rep
        if action == "ranger":
            plan = srv.plans.pop(str(dossier), None)
            if not plan:
                raise Refus("Clique d'abord sur « Ranger les doublons » pour voir ce qui va bouger.")
            return {"texte": ranger(dossier, plan), "fait": True}
        if action == "restaurer":
            return {"texte": restaurer(dossier), "restaure": True}
        raise Refus("Action inconnue.")
    except (Refus, drives.Refus) as e:
        return {"texte": str(e), "erreur": True}
    except Exception as e:  # jamais de page muette : l'erreur est dite en clair
        return {"texte": f"Erreur inattendue : {e}", "erreur": True}


def page(jeton):
    puces = "".join(f'<button class="puce" data-c="{html.escape(c)}">{html.escape(nom)}</button>' for nom, c in raccourcis())
    trouves = [nom for nom, present in outils() if present]
    pied = "Outils en plus trouvés (facultatifs) : " + ", ".join(trouves) if trouves else ""
    lieux = [("mac", "Ce Mac" if sys.platform == "darwin" else "Ce PC")] + ([("icloud", "iCloud Drive")] if icloud() else []) \
        + [(k, d[0]) for k, d in drives.DRIVES.items()]
    lieux = "".join(f'<button class="puce lieu" data-l="{k}">{html.escape(nom)}</button>' for k, nom in lieux)
    etat = json.dumps({**drives.etat(), "icloud": icloud()}, ensure_ascii=False).replace("</", "<\\/")
    return (PAGE.replace("{RACCOURCIS}", puces).replace("{LIEUX}", lieux).replace("{OUTILS}", html.escape(pied))
            .replace("{ETAT}", etat).replace("{JETON}", jeton))


ICONE = ('<svg viewBox="0 0 64 64" width="88" height="88" aria-hidden="true"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
         '<stop offset="0" stop-color="#5ac8fa"/><stop offset="1" stop-color="#0a5cff"/></linearGradient></defs>'
         '<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/><circle cx="32" cy="32" r="17" fill="none" stroke="#fff" '
         'stroke-opacity=".35" stroke-width="7"/><path d="M32 15a17 17 0 1 1-17 17" fill="none" stroke="#fff" stroke-width="7" '
         'stroke-linecap="round"/></svg>')

PAGE = r"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaveSpace Drive</title>
<style>
:root{color-scheme:light dark;--fond:#f5f5f7;--carte:#fff;--texte:#1d1d1f;--doux:#6e6e73;--trait:rgba(0,0,0,.09);--accent:#007aff;
--accent2:#5ac8fa;--rouge:#d70015;--vert:#28a745;--ombre:0 1px 2px rgba(0,0,0,.05),0 6px 20px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root{--fond:#1c1c1e;--carte:#2c2c2e;--texte:#f5f5f7;--doux:#98989d;--trait:rgba(255,255,255,.1);
--accent:#0a84ff;--accent2:#64d2ff;--rouge:#ff453a;--vert:#30d158;--ombre:none}}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body{min-height:100vh;display:flex;flex-direction:column;user-select:none;-webkit-user-select:none}
button{font:inherit;color:inherit;border:0;background:none;cursor:pointer;-webkit-tap-highlight-color:transparent}
button:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 50%,transparent);outline-offset:2px}
button:disabled{opacity:.45;cursor:default}
header{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--trait)}
header svg{width:24px;height:24px}header .nom{font-weight:600;flex:1}
.bouton2{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;background:var(--carte);box-shadow:0 0 0 1px var(--trait);font-weight:500}
.bouton2:hover:not(:disabled){box-shadow:0 0 0 1px var(--accent)}
main{flex:1;width:100%;max-width:980px;margin:0 auto;padding:22px 24px}
.dossiers{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.puce{padding:7px 15px;border-radius:999px;background:var(--carte);box-shadow:0 0 0 1px var(--trait)}
#lieux{margin-bottom:10px;align-items:center}.ou{color:var(--doux);font-size:13px;margin-right:4px}
.puce:hover:not(:disabled){box-shadow:0 0 0 1px var(--accent)}.puce.choisie{background:var(--accent);color:#fff;box-shadow:none}
#saisie{display:block;margin:10px auto 0;width:min(520px,100%);font:inherit;padding:8px 12px;border-radius:8px;border:1px solid var(--trait);background:var(--carte);color:var(--texte)}
#chemin{text-align:center;color:var(--doux);font-size:12px;margin-top:8px;min-height:1.2em;word-break:break-all}
.heros{text-align:center;padding:26px 0 22px}
.heros svg{display:block;margin:0 auto}
.chiffre{font-size:68px;font-weight:700;letter-spacing:-.025em;line-height:1.05;background:linear-gradient(135deg,var(--accent2),var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent}
h1{font-size:26px;font-weight:700;margin:12px 0 6px;letter-spacing:-.01em}.chiffre+h1{margin-top:0;font-size:20px;font-weight:600}
.sous{color:var(--doux);margin:0 auto;max-width:540px}
.principal{margin-top:22px;padding:13px 42px;border-radius:999px;background:var(--accent);color:#fff;font-size:17px;font-weight:600;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 35%,transparent);transition:transform .08s}
.principal:active:not(:disabled){transform:scale(.97)}
.lien{display:block;margin:12px auto 0;color:var(--accent);font-size:14px}.lien:hover{text-decoration:underline}
.roue{width:72px;height:72px;border-radius:50%;border:6px solid var(--trait);border-top-color:var(--accent);animation:tourne .9s linear infinite;margin:8px auto}
@keyframes tourne{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){.roue{animation-duration:3s}}
.coche{width:76px;height:76px;margin:6px auto;border-radius:50%;background:var(--vert);display:grid;place-items:center}
#message{max-width:560px;margin:0 auto 18px;padding:10px 14px;border-radius:10px;white-space:pre-wrap;font-size:14px}
#message.info{background:color-mix(in srgb,var(--accent) 13%,transparent)}#message.erreur{background:color-mix(in srgb,var(--rouge) 15%,transparent)}
.cartes{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}@media (max-width:760px){.cartes{grid-template-columns:1fr}}
.carte{background:var(--carte);border-radius:14px;padding:18px;box-shadow:var(--ombre),0 0 0 1px var(--trait);min-width:0}
.ico{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;color:#fff}
.carte h2{font-size:14px;font-weight:600;margin:12px 0 0;color:var(--doux)}.valeur{font-size:26px;font-weight:700;letter-spacing:-.01em}
.carte p{color:var(--doux);margin:4px 0 0;font-size:13px}
summary{cursor:pointer;color:var(--accent);font-size:13px;margin-top:10px}
.liste{max-height:230px;overflow:auto;margin-top:8px;font-size:12.5px;user-select:text;-webkit-user-select:text}
.liste div{display:flex;gap:8px;padding:5px 0;border-top:1px solid var(--trait);overflow-wrap:anywhere}
.liste .t{margin-left:auto;color:var(--doux);white-space:nowrap}.liste .garde{font-weight:600}.liste .trop{color:var(--doux);padding-left:12px}
#note{text-align:center;color:var(--doux);font-size:12px;margin-top:14px}
#voile{position:fixed;inset:0;background:rgba(0,0,0,.38);display:grid;place-items:center;padding:24px;-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}
.feuille{background:var(--carte);border-radius:16px;max-width:580px;width:100%;padding:24px;box-shadow:0 24px 70px rgba(0,0,0,.35);max-height:86vh;display:flex;flex-direction:column}
.feuille h1{margin-top:0}.feuille .liste{max-height:none;flex:1;border-bottom:1px solid var(--trait)}
.actions{display:flex;justify-content:flex-end;gap:10px;margin-top:18px}.actions .principal{margin:0;padding:9px 22px;font-size:15px}
footer{text-align:center;color:var(--doux);font-size:11.5px;padding:14px 20px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
</style>
<header>{ICONE}<span class="nom">SaveSpace Drive</span>
<button class="bouton2" id="restaurer" title="Remet à leur place d'origine les fichiers mis de côté dans ce dossier">
<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>Annuler / restaurer</button></header>
<main>
<div class="dossiers" id="lieux"><span class="ou">Où chercher ?</span>{LIEUX}</div>
<div class="dossiers" id="dossiers">{RACCOURCIS}<button class="puce" id="autre">Autre dossier…</button></div>
<input id="saisie" hidden placeholder="Colle ici le chemin d'un dossier, puis appuie sur Entrée">
<div id="chemin"></div>
<section class="heros"><div id="logo">{ICONE}</div><div class="roue" id="roue" hidden></div>
<div class="coche" id="coche" hidden><svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg></div>
<div class="chiffre" id="chiffre" hidden></div><h1 id="titre"></h1><p class="sous" id="sous"></p>
<button class="principal" id="principal">Analyser</button><button class="lien" id="lien" hidden></button>
<a class="lien" id="ext" target="_blank" rel="noopener" hidden></a></section>
<div id="message" hidden></div>
<section class="cartes" id="cartes" hidden>
<div class="carte" id="c-doublons"><div class="ico" style="background:#0a84ff"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/></svg></div>
<h2>Doublons</h2><div class="valeur"></div><p></p><details><summary>Voir la liste</summary><div class="liste"></div></details></div>
<div class="carte" id="c-gros"><div class="ico" style="background:#ff9f0a"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M5 20V10M12 20V4M19 20v-7"/></svg></div>
<h2>Gros fichiers</h2><div class="valeur"></div><p></p><details><summary>Voir la liste</summary><div class="liste"></div></details></div>
<div class="carte" id="c-caches"><div class="ico" style="background:#bf5af2"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4.5h6V7M6 7l1 13h10l1-13"/></svg></div>
<h2 id="t-caches">Caches et journaux</h2><div class="valeur"></div><p></p><details><summary>Voir la liste</summary><div class="liste"></div></details></div>
</section><div id="note"></div>
</main>
<footer><span>Rien n'est envoyé chez nous. Un drive en ligne n'est contacté que si tu le connectes, pour lire la liste de tes fichiers.</span><span>{OUTILS}</span><button class="lien" id="quitter" style="margin:0;font-size:inherit">Quitter</button></footer>
<div id="voile" hidden><div class="feuille" role="dialog" aria-modal="true" aria-labelledby="f-titre">
<h1 id="f-titre"></h1><p class="sous" id="f-texte" style="margin:0 0 14px;max-width:none"></p><div class="liste" id="f-liste"></div>
<div class="actions"><button class="bouton2" id="f-non">Annuler</button><button class="principal" id="f-oui"></button></div></div></div>
<script>
const J="{JETON}",$=i=>document.getElementById(i),n=(k,m)=>k+" "+m+(k>1?"s":"");
const E={ETAT};let lieu="mac",drive="";
const ICLOUD="iCloud Drive va être examiné. Les fichiers restés dans le nuage ne sont pas téléchargés : ils sont seulement comptés. Attention : mettre un fichier de côté ici le retire aussi de tous tes appareils (iPhone, iPad…) ; il reste dans « quarantaine » et revient avec « Annuler / restaurer ».";
let dossier="",nom="",suite=null,suiteLien=null,chrono=null,dernier=null,vue=null,natif=false;
function msg(t,genre){$("message").textContent=t||"";$("message").className=genre||"";$("message").hidden=!t}
function heros(o){for(const i of["logo","roue","coche"])$(i).hidden=o.icone!==i;
 $("chiffre").hidden=!o.chiffre;$("chiffre").textContent=o.chiffre||"";$("titre").textContent=o.titre||"";$("sous").textContent=o.sous||"";
 $("principal").hidden=!o.bouton;$("principal").textContent=o.bouton||"";$("principal").disabled=false;suite=o.action;
 $("lien").hidden=!o.lien;$("lien").textContent=o.lien||"";suiteLien=o.actionLien;
 $("ext").hidden=!o.ext;$("ext").href=o.ext||"#";$("ext").textContent=o.extTexte||""}
function bloque(oui){document.querySelectorAll(".puce,#restaurer").forEach(b=>b.disabled=oui)}
function accueil(){vue=accueil;$("cartes").hidden=true;$("note").textContent="";
 if(drive){const D=E[drive];
  if(!E.rclone)return heros({icone:"logo",titre:D.nom,sous:"Pour "+D.nom+", SaveSpace Drive utilise le moteur gratuit rclone : il est inclus dans l'app téléchargée, mais introuvable ici."});
  if(!D.ok)return heros({icone:"logo",titre:"Connecte "+D.nom,sous:"Ton navigateur va s'ouvrir sur la page de connexion de "+D.nom+" : SaveSpace Drive ne voit jamais ton mot de passe. Ensuite, l'analyse lit seulement la liste de tes fichiers : rien n'est téléchargé.",bouton:"Connecter "+D.nom,action:connecter});
  return heros({icone:"logo",titre:"Retrouve de la place sur "+D.nom,sous:"Analyser lit seulement la liste de tes fichiers et leurs empreintes : rien n'est téléchargé, rien ne bouge.",bouton:"Analyser",action:analyser,lien:"Déconnecter "+D.nom,actionLien:deconnecter})}
 heros({icone:"logo",titre:"Retrouve de la place",sous:!dossier?"Choisis d'abord un dossier ci-dessus.":lieu==="icloud"?ICLOUD:"Le dossier « "+nom+" » va être examiné. Analyser regarde seulement : rien ne bouge sans ton accord.",bouton:"Analyser",action:analyser});
 $("principal").disabled=!dossier}
function travail(titre,attente){const t0=Date.now();$("cartes").hidden=true;$("note").textContent="";msg("");bloque(true);
 heros({icone:"roue",titre,sous:"Rien n'est modifié pendant ce temps."});clearInterval(chrono);
 chrono=setInterval(()=>{const s=Math.round((Date.now()-t0)/1000);if(s>=4)$("sous").textContent=(attente||(drive?"Un grand drive peut prendre quelques minutes…":"Un gros dossier peut prendre quelques minutes…"))+" "+s+" s"},1000)}
async function appel(a){const post=x=>fetch("/"+x,{method:"POST",headers:{"X-Jeton":J,"Content-Type":"application/json"},body:JSON.stringify({dossier,drive})}).then(r=>r.json());
 try{let d=await post(a);while(d.en_cours){await new Promise(f=>setTimeout(f,800));d=await post("suivre")}return d}
 catch(e){return{texte:"SaveSpace Drive ne répond plus. Ferme la fenêtre et relance-le.",erreur:true}}
 finally{clearInterval(chrono);bloque(false)}}
function lignes(el,ls){el.replaceChildren(...ls.map(([a,b,cl])=>{const d=document.createElement("div"),x=document.createElement("span"),y=document.createElement("span");
 if(cl)d.className=cl;x.textContent=a;y.className="t";y.textContent=b||"";d.append(x,y);return d}))}
function carte(id,valeur,texte,ls){const c=$(id);c.querySelector(".valeur").textContent=valeur;c.querySelector("p").textContent=texte;
 const det=c.querySelector("details");det.open=false;det.hidden=!ls.length;lignes(c.querySelector(".liste"),ls)}
function groupes(gs,total){const ls=gs.flatMap(g=>[["On garde : "+g.garde,g.taille,"garde"],...g.en_trop.map(c=>["en trop : "+c,"","trop"])]);
 if(total>gs.length)ls.push(["… et "+n(total-gs.length,"autre groupe"),""]);return ls}
function resultat(r){vue=()=>resultat(r);dernier=r;const D=r.drive,esp=r.espace?" "+r.espace+".":"";
 if(r.recuperables_octets>0)heros({chiffre:r.recuperables,titre:"récupérables",sous:D?"en mettant les doublons de "+D+" à la corbeille."+esp:"en rangeant les doublons de « "+nom+" » ("+r.total+" analysés).",bouton:D?"Mettre les doublons à la corbeille…":"Ranger les doublons…",action:preparer,lien:"Analyser à nouveau",actionLien:analyser});
 else heros({icone:"coche",titre:"Aucun doublon ici",sous:(D?D+" ("+r.total+") est déjà en ordre."+esp:"« "+nom+" » ("+r.total+") est déjà en ordre.")+" Jette un œil aux plus gros fichiers ci-dessous.",bouton:"Analyser à nouveau",action:analyser});
 $("cartes").hidden=false;
 carte("c-doublons",r.groupes?r.recuperables:"Aucun",r.groupes?n(r.groupes,"groupe")+" de fichiers identiques. On garde un exemplaire de chacun, le reste "+(D?"va dans la corbeille de "+D+".":"est mis de côté."):"Pas de fichier en double ici.",groupes(r.doublons,r.groupes));
 carte("c-gros",r.gros.length?r.gros[0][1]:"Aucun",r.gros.length?"pour le plus gros. Voici les plus lourds, à trier toi-même : on n'y touche pas.":"Ce dossier est vide.",r.gros);
 $("t-caches").textContent=D?"Corbeille et autres":"Caches et journaux";
 if(D)carte("c-caches",r.corbeille,"déjà dans la corbeille de "+D+" : la vider sur son site libère cette place."+(r.autres?" Google Photos et Gmail occupent "+r.autres+" : rapport seulement, on n'y touche pas.":""),[]);
 else carte("c-caches",r.caches?r.caches_taille:"Aucun",r.caches?n(r.caches,"fichier")+" de cache ou de journal. Ils se recréent tout seuls quand une app en a besoin.":"Pas de cache ni de journal dans ce dossier.",[]);
 $("note").textContent=[r.nuage,r.proteges?n(r.proteges,"fichier")+" sensibles (clés, .git) ignorés : on n'y touche jamais.":""].filter(Boolean).join(" ")}
async function deconnecter(){const d=await appel("deconnecter");if(d.erreur)return msg(d.texte,"erreur");E[drive].ok=false;accueil();
 $("ext").hidden=false;$("ext").href=d.lien;$("ext").textContent=d.lien_texte;msg(d.texte,"info")}
async function connecter(){travail("Connexion à "+nom+"…","Termine la connexion dans ton navigateur, puis reviens ici.");$("sous").textContent="Termine la connexion dans ton navigateur, puis reviens ici.";
 const d=await appel("connecter");if(!d.erreur)E[drive].ok=true;accueil();msg(d.texte,d.erreur?"erreur":"info")}
async function analyser(){travail("Analyse de « "+nom+" »…");const d=await appel("analyser");if(d.erreur){accueil();return msg(d.texte,"erreur")}resultat(d.resultat)}
async function preparer(){travail("Préparation de la liste exacte…");const d=await appel("preparer");vue();
 if(d.erreur)return msg(d.texte,"erreur");if(!d.confirmer)return msg(d.texte,"info");
 const D=d.drive;$("f-titre").textContent=D?"Mettre "+n(d.nombre,"fichier")+" à la corbeille de "+D+" ?":"Ranger "+n(d.nombre,"fichier")+" en trop ?";
 $("f-texte").textContent=D?d.taille+" iront dans la corbeille de "+D+". Tu peux les récupérer depuis cette corbeille pendant 30 jours : rien n'est effacé définitivement."
  :d.taille+" iront dans le dossier « "+d.quarantaine+" », à l'intérieur de « "+nom+" ». Rien n'est effacé : « Annuler / restaurer » remet tout en place quand tu veux."
  +(lieu==="icloud"?" Attention, c'est iCloud Drive : ces fichiers disparaissent aussi de tes autres appareils (iPhone, iPad…) tant que tu ne les restaures pas.":"");
 lignes($("f-liste"),groupes(d.plan,d.groupes));$("f-oui").textContent=D?"Oui, mettre "+n(d.nombre,"fichier")+" à la corbeille":"Oui, ranger "+n(d.nombre,"fichier");$("voile").hidden=false;$("f-non").focus()}
function fermer(){$("voile").hidden=true}
async function ranger(){fermer();travail("Rangement en cours…");const d=await appel("ranger");
 if(d.erreur){vue();return msg(d.texte,"erreur")}vue=()=>{};$("cartes").hidden=true;
 heros({icone:"coche",titre:"C'est fait",sous:d.texte.replace(/^C'est fait : /,""),bouton:"Analyser à nouveau",action:analyser,lien:drive?"":"Annuler ce rangement",actionLien:restaurer,ext:d.lien,extTexte:d.lien_texte})}
async function restaurer(){if(!dossier&&!drive)return msg("Choisis d'abord un dossier.","erreur");const avant=vue;travail("Remise en place…");const d=await appel("restaurer");
 if(d.erreur){(avant||accueil)();return msg(d.texte,"erreur")}vue=accueil;$("cartes").hidden=true;
 if(drive)return heros({icone:"logo",titre:"Récupérer depuis la corbeille",sous:d.texte,bouton:"Analyser",action:analyser,ext:d.lien,extTexte:d.lien_texte});
 heros({icone:"coche",titre:"Tout est revenu",sous:d.texte.replace(/^C'est fait : /,""),bouton:"Analyser à nouveau",action:analyser})}
function choisir(c){c=(c||"").trim();if(!c)return;dossier=c;const raccourci=document.querySelector('.puce[data-c="'+CSS.escape(c)+'"]');
 nom=raccourci?raccourci.textContent:c.split(/[\\/]/).filter(Boolean).pop()||c;$("chemin").textContent=raccourci?"":c;
 document.querySelectorAll("#dossiers .puce").forEach(b=>b.classList.toggle("choisie",b===raccourci||(b.id==="autre"&&!raccourci)));msg("");accueil()}
function choisirLieu(l){lieu=l;drive="";document.querySelectorAll(".lieu").forEach(b=>b.classList.toggle("choisie",b.dataset.l===l));
 $("dossiers").hidden=l!=="mac";$("saisie").hidden=true;$("chemin").textContent="";msg("");
 if(l==="mac"){const p=document.querySelector(".puce[data-c]");if(p)return choisir(p.dataset.c);dossier="";return accueil()}
 if(l==="icloud"){dossier=E.icloud;nom="iCloud Drive";return accueil()}
 dossier="";drive=l;nom=E[l].nom;accueil()}
document.querySelectorAll(".lieu").forEach(b=>b.onclick=()=>choisirLieu(b.dataset.l));
document.querySelectorAll(".puce[data-c]").forEach(b=>b.onclick=()=>{$("saisie").hidden=true;choisir(b.dataset.c)});
$("autre").onclick=async()=>{if(natif){const c=await window.pywebview.api.choisir();if(c)choisir(c)}else{$("saisie").hidden=false;$("saisie").focus()}};
$("saisie").onchange=()=>choisir($("saisie").value);
$("principal").onclick=()=>suite&&suite();$("lien").onclick=()=>suiteLien&&suiteLien();$("restaurer").onclick=restaurer;
$("f-non").onclick=()=>{fermer();msg("Rien n'a bougé.","info")};$("f-oui").onclick=ranger;
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("voile").hidden)$("f-non").click()});
$("quitter").onclick=async()=>{await fetch("/quitter",{method:"POST",headers:{"X-Jeton":J}}).catch(()=>0);document.body.replaceChildren();document.body.append("SaveSpace Drive est fermé. Tu peux fermer cet onglet.")};
window.addEventListener("pywebviewready",()=>{natif=true;$("quitter").hidden=true});
choisirLieu("mac");
</script></html>""".replace("{ICONE}", ICONE)


class Serveur(ThreadingHTTPServer):
    def server_close(self):  # l'app se ferme : un rclone encore en route (connexion abandonnée) part avec elle
        drives.arreter()
        super().server_close()

    def server_bind(self):  # sans socket.getfqdn : dans l'app Mac, cette résolution de nom inutile bloquait 35 s au lancement
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


def creer_serveur():
    s = Serveur(("127.0.0.1", 0), Ecran)  # 127.0.0.1 seulement, port libre choisi par le système
    s.daemon_threads, s.timeout = True, 0.5
    s.jeton, s.plans, s.fini, s.fil, s.rep = secrets.token_urlsafe(16), {}, False, None, None
    s.hote = f"127.0.0.1:{s.server_port}"
    return s, f"http://{s.hote}/?t={s.jeton}"


def principal(argv=None):
    s, url = creer_serveur()
    print("SaveSpace Drive s'ouvre dans ton navigateur.\n"
          f"Si rien ne s'ouvre, copie cette adresse dans ton navigateur : {url}\n"
          "Pour quitter : bouton « Quitter » de la page (ou Ctrl+C ici).", flush=True)
    webbrowser.open(url)
    try:
        while not s.fini:
            s.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        s.server_close()
    print("SaveSpace Drive est fermé.")
    return 0
