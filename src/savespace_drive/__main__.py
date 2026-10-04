"""`python -m savespace_drive` : ouvre l'écran local (APP1)."""
import sys
from savespace_drive.app import principal

sys.exit(principal(sys.argv[1:]))
