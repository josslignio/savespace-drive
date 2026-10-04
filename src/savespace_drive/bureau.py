"""Application de bureau (APP2) : la page d'APP1 dans une vraie fenêtre (pywebview : WKWebView sur Mac,
Edge WebView2 sur Windows). Aucune logique ici : le serveur local et la page sont ceux d'app.py.
Sans pywebview installé, on retombe sur l'écran dans le navigateur (app.principal)."""
import os, sys, threading
from savespace_drive import app

FRANCAIS = {"global.quitConfirmation": "Veux-tu vraiment quitter ?", "global.ok": "OK", "global.quit": "Quitter",
            "global.cancel": "Annuler", "cocoa.menu.about": "À propos de", "cocoa.menu.services": "Services",
            "cocoa.menu.view": "Présentation", "cocoa.menu.edit": "Édition", "cocoa.menu.hide": "Masquer",
            "cocoa.menu.hideOthers": "Masquer les autres", "cocoa.menu.showAll": "Tout afficher", "cocoa.menu.quit": "Quitter",
            "cocoa.menu.fullscreen": "Plein écran", "cocoa.menu.cut": "Couper", "cocoa.menu.copy": "Copier",
            "cocoa.menu.paste": "Coller", "cocoa.menu.selectAll": "Tout sélectionner"}


class Api:  # appelée par la page (window.pywebview.api) : seulement le sélecteur de dossier du système
    fenetre = None

    def choisir(self):
        import webview
        choix = self.fenetre.create_file_dialog(webview.FileDialog.FOLDER)
        return choix[0] if choix else ""


def servir(s, fenetre):
    while not s.fini:
        s.handle_request()
    fenetre.destroy()  # « Quitter » ou fermeture : la fenêtre part avec le serveur


def principal(argv=None):
    try:
        import webview
    except ImportError:
        return app.principal(argv)
    s, url = app.creer_serveur()
    if sys.stdout:  # fenêtre sans console (Windows) : sys.stdout vaut None
        print(f"SaveSpace Drive : {url}", flush=True)
    api = Api()
    api.fenetre = webview.create_window("SaveSpace Drive", url, js_api=api, width=1040, height=780,
                                        min_size=(720, 560))
    api.fenetre.events.closed += lambda: setattr(s, "fini", True)
    threading.Thread(target=servir, args=(s, api.fenetre), daemon=True).start()
    try:
        webview.start(localization=FRANCAIS)
    finally:
        s.fini = True
        s.server_close()
    # pywebview laisse un fil non « daemon » (injection du JS) bloqué pour toujours si la fenêtre se ferme pendant
    # le chargement : Python l'attendrait sans fin (processus fantôme mesuré : 1 essai de fumée sur 9). On n'attend pas.
    if sys.stdout:
        sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(principal())
