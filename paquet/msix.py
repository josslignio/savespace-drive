"""Paquet MSIX de SaveSpace Drive pour le Microsoft Store — NON signé par nous : le Store le re-signe avec le certificat
de Microsoft (donc pas d'écran SmartScreen). À lancer sur Windows APRÈS paquet/construire.py (dist/SaveSpace Drive.exe).
Identité Store (Partner Center → l'app → Gestion du produit → Identité du produit), lue dans l'environnement :
  MSIX_IDENTITY_NAME (Package/Identity/Name), MSIX_PUBLISHER (Package/Identity/Publisher, « CN=… »),
  MSIX_PUBLISHER_DISPLAY_NAME (Package/Properties/PublisherDisplayName). Sans elles : valeurs A_REMPLACER (refusées par le Store).
Usage : python paquet/msix.py [--sans-makeappx]   (--sans-makeappx : prépare le dossier sans emballer, pour l'essai hors Windows)"""
import glob, os, re, shutil, subprocess, sys
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image

RACINE = Path(__file__).resolve().parents[1]
DIST, SCENE = RACINE / "dist", RACINE / "build" / "msix"
ICONE = Image.open(RACINE / "paquet" / "icone" / "SaveSpace.png").convert("RGBA")
LOGOS = {"StoreLogo": (50, 50), "Square44x44Logo": (44, 44), "Square150x150Logo": (150, 150), "Wide310x150Logo": (310, 150)}
IDENTITE = {"IDENTITY_NAME": ("MSIX_IDENTITY_NAME", "A-REMPLACER.SaveSpaceDrive"),
            "PUBLISHER": ("MSIX_PUBLISHER", "CN=A-REMPLACER-PAR-PARTNER-CENTER"),
            "PUBLISHER_DISPLAY_NAME": ("MSIX_PUBLISHER_DISPLAY_NAME", "A REMPLACER")}


def version_msix(v):  # le Store exige 4 nombres, le dernier à 0 : « v0.1.0 » → 0.1.0.0 ; « 0.0.0-essai » → 0.0.0.0
    nombres = (re.findall(r"\d+", v.split("-")[0]) + ["0", "0", "0"])[:3]
    return ".".join(nombres + ["0"])


def logo(nom, taille):
    w, h = taille
    cote = min(w, h)
    toile = Image.new("RGBA", taille, (0, 0, 0, 0))
    toile.paste(ICONE.resize((cote, cote), Image.LANCZOS), ((w - cote) // 2, (h - cote) // 2))
    toile.save(SCENE / "Assets" / f"{nom}.png")


def makeappx():
    trouves = glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe")
    if not trouves:
        sys.exit("makeappx.exe introuvable : installer le SDK Windows 10/11.")
    return max(trouves, key=lambda p: [int(n) for n in re.findall(r"\d+", Path(p).parts[-3])])


def principal():
    valeurs = {cle: os.environ.get(var) or defaut for cle, (var, defaut) in IDENTITE.items()}
    valeurs["VERSION"] = version_msix(os.environ.get("VERSION", "0.1.1"))
    for cle, (var, _) in IDENTITE.items():
        if "REMPLACER" in valeurs[cle]:
            print(f"ATTENTION : {var} absent — paquet construit avec un faux nom, refusé par le Store.")
    shutil.rmtree(SCENE, ignore_errors=True)
    (SCENE / "Assets").mkdir(parents=True)
    manifeste = (RACINE / "paquet" / "AppxManifest.xml").read_text(encoding="utf-8")
    for cle, val in valeurs.items():
        manifeste = manifeste.replace("{{" + cle + "}}", escape(val, {'"': "&quot;"}))
    (SCENE / "AppxManifest.xml").write_text(manifeste, encoding="utf-8")
    for nom, taille in LOGOS.items():
        logo(nom, taille)
    if "--sans-makeappx" in sys.argv:
        print(f"préparé (sans emballer) : {SCENE}")
        return
    shutil.copy2(DIST / "SaveSpace Drive.exe", SCENE / "SaveSpaceDrive.exe")
    sortie = DIST / f"SaveSpace-Drive-{valeurs['VERSION']}-store.msix"
    subprocess.run([makeappx(), "pack", "/d", str(SCENE), "/p", str(sortie), "/o"], check=True)
    print(f"construit (non signé, pour le Store) : {sortie}")


if __name__ == "__main__":
    principal()
