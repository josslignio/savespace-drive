"""Construit l'app de bureau avec PyInstaller (outil existant) — à lancer sur le système visé.
Mac : dist/SaveSpace Drive.app puis dist/SaveSpace-Drive-<version>-mac.dmg (hdiutil, fourni avec macOS).
Windows : dist/SaveSpace Drive.exe (un seul fichier) ; l'installeur se fait ensuite avec paquet/windows.iss (Inno Setup).
Le moteur rclone (MIT) est inclus : binaire OFFICIEL téléchargé sur downloads.rclone.org, refusé si son SHA256 diffère
de l'empreinte épinglée ici OU de celle publiée dans SHA256SUMS. Mac : les deux puces réunies (lipo). Aucun Homebrew.
Usage : python paquet/construire.py   (variables facultatives : VERSION=0.1.1, ARCH=universal2)"""
import hashlib, io, os, plistlib, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path
import PyInstaller.__main__

RACINE = Path(__file__).resolve().parents[1]
ICONE, DIST, TRAVAIL = RACINE / "paquet" / "icone", RACINE / "dist", RACINE / "build"
NOM, VERSION = "SaveSpace Drive", os.environ.get("VERSION", "0.1.1").lstrip("v")
RCLONE = "v1.75.1"  # empreintes relevées le 04/10/2026 dans https://downloads.rclone.org/v1.75.1/SHA256SUMS (signé PGP)
RCLONE_ZIP = {"osx-arm64": "c61d7a371c62bcbbe882c3423aa4b8bf63485c248dd0f692997b8f0c3f6d0c6f",
              "osx-amd64": "29253d0288b8fbbac46baad6e5f6add6cb01d462c79f10805bbd4631c4cdf82c",
              "windows-amd64": "200eb602c126d82aa38b51e0f6b9ae837473ff99b51278d3f6f837574c494d6e"}


def _lire(url, delai):  # downloads.rclone.org refuse l'agent « Python-urllib » (403 mesuré)
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "savespace-drive-construire"}), timeout=delai).read()


def rclone():
    """Le rclone officiel, vérifié, prêt à inclure : build/rclone/rclone (Mac, universel) ou rclone.exe (Windows)."""
    base = f"https://downloads.rclone.org/{RCLONE}"
    publiees = _lire(f"{base}/SHA256SUMS", 60).decode().splitlines()
    dossier, win = TRAVAIL / "rclone", sys.platform == "win32"
    dossier.mkdir(parents=True, exist_ok=True)
    pieces = []
    for cible in ("windows-amd64",) if win else ("osx-arm64", "osx-amd64"):
        nom = f"rclone-{RCLONE}-{cible}"
        octets = _lire(f"{base}/{nom}.zip", 600)
        h = hashlib.sha256(octets).hexdigest()
        if h != RCLONE_ZIP[cible] or f"{h}  {nom}.zip" not in publiees:
            raise SystemExit(f"{nom}.zip : SHA256 inattendu ({h}) — rien n'est construit")
        with zipfile.ZipFile(io.BytesIO(octets)) as z:
            (dossier / cible).write_bytes(z.read(f"{nom}/rclone" + (".exe" if win else "")))
        pieces.append(str(dossier / cible))
    final = dossier / ("rclone.exe" if win else "rclone")
    if win:
        os.replace(pieces[0], final)
    else:
        subprocess.run(["lipo", "-create", "-output", str(final), *pieces], check=True)
    final.chmod(0o755)
    print(f"rclone {RCLONE} vérifié (SHA256 épinglé = publié) : {final}")
    return final


def principal():
    args = [str(RACINE / "paquet" / "lanceur.py"), "--name", NOM, "--windowed", "--noconfirm", "--clean",
            "--distpath", str(DIST), "--workpath", str(TRAVAIL), "--specpath", str(TRAVAIL), "--paths", str(RACINE / "src"),
            "--collect-data", "savespace_drive",  # versions_gellees.json (doctor --strict)
            "--add-binary", f"{rclone()}{os.pathsep}.", "--add-data", f"{RACINE / 'THIRD_PARTY'}{os.pathsep}THIRD_PARTY"]
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
