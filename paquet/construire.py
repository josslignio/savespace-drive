"""Construit l'app de bureau avec PyInstaller (outil existant) — à lancer sur le système visé.
Mac : dist/SaveSpace Drive.app puis dist/SaveSpace-Drive-<version>-mac.dmg (hdiutil, fourni avec macOS).
Windows : dist/SaveSpace Drive.exe (un seul fichier) ; l'installeur se fait ensuite avec paquet/windows.iss (Inno Setup).
Usage : python paquet/construire.py   (variables facultatives : VERSION=0.1.0, ARCH=universal2)"""
import os, plistlib, shutil, subprocess, sys
from pathlib import Path
import PyInstaller.__main__

RACINE = Path(__file__).resolve().parents[1]
ICONE, DIST, TRAVAIL = RACINE / "paquet" / "icone", RACINE / "dist", RACINE / "build"
NOM, VERSION = "SaveSpace Drive", os.environ.get("VERSION", "0.1.0").lstrip("v")


def principal():
    args = [str(RACINE / "paquet" / "lanceur.py"), "--name", NOM, "--windowed", "--noconfirm", "--clean",
            "--distpath", str(DIST), "--workpath", str(TRAVAIL), "--specpath", str(TRAVAIL), "--paths", str(RACINE / "src"),
            "--collect-data", "savespace_drive"]  # versions_gellees.json (doctor --strict)
    if sys.platform == "darwin":
        args += ["--icon", str(ICONE / "SaveSpace.icns"), "--osx-bundle-identifier", "io.github.savespacedrive"]
        args += ["--target-arch", os.environ["ARCH"]] if os.environ.get("ARCH") else []
    else:
        args += ["--onefile", "--icon", str(ICONE / "SaveSpace.ico")]
    PyInstaller.__main__.run(args)
    if sys.platform == "darwin":
        mac()


def mac():
    app = DIST / f"{NOM}.app"
    plist = app / "Contents" / "Info.plist"
    infos = plistlib.loads(plist.read_bytes())
    infos.update(CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION, CFBundleDevelopmentRegion="fr",
                 LSApplicationCategoryType="public.app-category.utilities", NSHighResolutionCapable=True,
                 NSHumanReadableCopyright="Logiciel libre (MIT). Tout reste sur ton ordinateur.")
    plist.write_bytes(plistlib.dumps(infos))
    # signature « ad hoc » (sans compte développeur) refaite après la retouche d'Info.plist, sinon l'app est dite abîmée
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    scene = TRAVAIL / "dmg"
    shutil.rmtree(scene, ignore_errors=True)
    scene.mkdir(parents=True)
    subprocess.run(["ditto", str(app), str(scene / app.name)], check=True)
    (scene / "Applications").symlink_to("/Applications")  # glisser l'app sur ce raccourci = l'installer
    dmg = DIST / f"SaveSpace-Drive-{VERSION}-mac.dmg"
    dmg.unlink(missing_ok=True)
    subprocess.run(["hdiutil", "create", "-volname", NOM, "-srcfolder", str(scene), "-fs", "HFS+", "-format", "UDZO",
                    "-ov", str(dmg)], check=True)
    print(f"construit : {app}\nconstruit : {dmg}")


if __name__ == "__main__":
    principal()
