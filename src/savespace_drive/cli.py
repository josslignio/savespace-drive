"""savespace_drive.cli : routeur unique vers les dix commandes existantes (DN8L), plus « app » (APP1) et « bureau » (APP2).
Importe chaque module par son nom au moment de la délégation et lui transmet
l'argv restant tel quel ; aucune logique de ces modules n'est réécrite ici.
Dans un terminal, la sortie est traduite en phrases simples (APP0, lisible.py) ;
avec --json, ou si la sortie est redirigée, ce sont les octets d'origine."""
import sys

_COMMANDES = (
    "doctor", "analyse", "doublons", "similaires", "gros",
    "caches", "decharge", "range", "restaure", "tout", "app", "bureau",
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    brut = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if not argv or argv[0] not in _COMMANDES:
        print("usage : savespace-drive {" + "|".join(_COMMANDES) + "} ... [--json]\n"
              "le plus simple : savespace-drive bureau  (ouvre la fenêtre ; app = dans le navigateur)",
              file=sys.stderr)
        return 2
    nom, reste = argv[0], argv[1:]
    if nom == "app":
        from savespace_drive import app
        return app.principal(reste)
    if nom == "bureau":
        from savespace_drive import bureau
        return bureau.principal(reste)
    if brut or not sys.stdout.isatty():
        return _deleguer(nom, reste)
    from savespace_drive import lisible
    return lisible.lisible(nom, reste, _deleguer)


def _deleguer(nom, reste):
    if nom == "doctor":
        from savespace_drive import doctor
        return doctor.principal(reste)
    if nom == "analyse":
        from savespace_drive import analyse
        return analyse.principal(reste)
    if nom == "doublons":
        from savespace_drive import doublons
        return doublons.principal(reste)
    if nom == "similaires":
        from savespace_drive import similaires
        return similaires._principal(reste)
    if nom == "gros":
        from savespace_drive import gros
        return gros.principal(reste)
    if nom == "caches":
        from savespace_drive import caches
        return caches.principal(reste)
    if nom == "decharge":
        from savespace_drive import decharge
        return decharge.principal(reste)
    if nom == "range":
        from savespace_drive import range as _range
        return _range.principal(reste)
    if nom == "restaure":
        from savespace_drive import quarantaine
        return quarantaine.restaure(reste[0] if reste else "quarantaine/manifeste.json")
    from savespace_drive import tout
    return tout.principal(reste)


if __name__ == "__main__":
    sys.exit(main())
