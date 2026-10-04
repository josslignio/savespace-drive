"""Point d'entrée de l'app empaquetée (PyInstaller) : ouvre la fenêtre SaveSpace Drive."""
import sys
from savespace_drive.bureau import principal

sys.exit(principal())
