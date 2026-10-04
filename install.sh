#!/bin/sh
# Installe SaveSpace Drive sur Mac, en une ligne, sans écran d'avertissement :
#   curl -fsSL https://raw.githubusercontent.com/josslignio/savespace-drive/main/install.sh | sh
# Télécharge le dernier .dmg publié (GitHub Releases), copie l'app dans /Applications (ou ~/Applications),
# puis efface tout ce qu'il a créé. Sans sudo. Relançable sans risque : remplace l'app par la dernière version.
# Un fichier téléchargé par curl ne porte pas la marque « quarantaine » : macOS ouvre l'app sans avertir.
set -eu

DEPOT="josslignio/savespace-drive"   # propriétaire/nom du dépôt GitHub — à fixer le jour de la publication

APP="SaveSpace Drive.app"
API="${SAVESPACE_API:-https://api.github.com}"                  # essais seulement
DMG_URL="${SAVESPACE_DMG_URL:-}"                                 # essais seulement (ex. file:///…/app.dmg)
DESTINATION="${SAVESPACE_APPLICATIONS:-/Applications}"           # essais seulement
REPLI="${SAVESPACE_APPLICATIONS_REPLI:-$HOME/Applications}"      # essais seulement

echec() { echo "SaveSpace Drive : échec — $1" >&2; exit 1; }

TRAVAIL=""
VOLUME=""
menage() {
  if [ -n "$VOLUME" ]; then hdiutil detach "$VOLUME" -quiet -force >/dev/null 2>&1 || true; fi
  if [ -n "$TRAVAIL" ]; then rm -rf "$TRAVAIL"; fi
  if [ -n "${CIBLE:-}" ]; then rm -rf "$CIBLE/.$APP.partiel"; fi
}
trap menage EXIT
trap 'exit 1' INT TERM HUP

principal() {  # tout le script est lu avant de s'exécuter (sûr avec « curl | sh », même coupé en route)
[ "$(uname -s)" = "Darwin" ] || echec "ce script est pour Mac. Sur Windows : voir le README."
command -v curl >/dev/null && command -v hdiutil >/dev/null || echec "curl ou hdiutil introuvable."

if [ -z "$DMG_URL" ]; then
  case "$DEPOT" in A_REMPLACER/*) echec "pas encore publié (dépôt non renseigné dans install.sh)." ;; esac
  echo "Recherche de la dernière version…"
  INFOS="$(curl -fsSL "$API/repos/$DEPOT/releases/latest")" \
    || echec "aucune version publiée trouvée pour $DEPOT, ou pas de connexion Internet."
  DMG_URL="$(printf '%s\n' "$INFOS" | grep -o '"browser_download_url": *"[^"]*\.dmg"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')"
  [ -n "$DMG_URL" ] || echec "aucun fichier .dmg dans la dernière version publiée de $DEPOT."
fi

TRAVAIL="$(mktemp -d "${TMPDIR:-/tmp}/savespace-install.XXXXXX")" || echec "impossible de créer un dossier de travail."
echo "Téléchargement de $DMG_URL"
curl -fL --progress-bar -o "$TRAVAIL/app.dmg" "$DMG_URL" || echec "téléchargement impossible ($DMG_URL)."

mkdir "$TRAVAIL/volume"
VOLUME="$TRAVAIL/volume"
hdiutil attach "$TRAVAIL/app.dmg" -nobrowse -readonly -noautoopen -mountpoint "$TRAVAIL/volume" -quiet </dev/null \
  || echec "le fichier téléchargé n'est pas une image disque lisible."
[ -d "$VOLUME/$APP" ] || echec "« $APP » absent de l'image disque."

if [ -d "$DESTINATION" ] && [ -w "$DESTINATION" ]; then CIBLE="$DESTINATION"
else
  mkdir -p "$REPLI" || echec "impossible de créer $REPLI."
  CIBLE="$REPLI"
fi
if pgrep -f "$CIBLE/$APP/Contents/MacOS/" >/dev/null 2>&1; then
  echec "SaveSpace Drive est ouvert. Quitte-le, puis relance cette commande."
fi

rm -rf "$CIBLE/.$APP.partiel"
ditto "$VOLUME/$APP" "$CIBLE/.$APP.partiel" || echec "copie impossible vers $CIBLE (disque plein ?)."
rm -rf "$CIBLE/$APP" || echec "impossible de remplacer l'ancienne version dans $CIBLE."
mv "$CIBLE/.$APP.partiel" "$CIBLE/$APP" || echec "impossible d'installer dans $CIBLE."

echo "SaveSpace Drive est installé : $CIBLE/$APP"
echo "Ouvre-le depuis le Launchpad ou le dossier Applications."
}

principal "$@"
