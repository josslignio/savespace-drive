"""Icône de l'app, dessinée ici (aucun logo tiers) : carré arrondi bleu dégradé, anneau blanc aux trois quarts.
Produit paquet/icone/SaveSpace.png (1024 px), .icns (Mac, via iconutil) et .ico (Windows). Outil de construction : Pillow."""
import math, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw

ICI = Path(__file__).resolve().parent / "icone"
N = 1024


def dessiner():
    x = 4  # suréchantillonnage, pour des bords nets
    t = N * x
    haut, bas = (90, 200, 250), (10, 92, 255)
    v = Image.linear_gradient("L").resize((t, t))
    degrade = ImageChops.add(v, v.transpose(Image.Transpose.ROTATE_90).transpose(Image.Transpose.FLIP_LEFT_RIGHT), scale=2.0)
    fond = Image.composite(Image.new("RGBA", (t, t), bas + (255,)), Image.new("RGBA", (t, t), haut + (255,)), degrade)
    masque = Image.new("L", (t, t))
    m = 100 * x  # marge de la grille d'icônes macOS (824 px utiles sur 1024)
    ImageDraw.Draw(masque).rounded_rectangle((m, m, t - m, t - m), radius=185 * x, fill=255)
    icone = Image.new("RGBA", (t, t))
    icone.paste(fond, mask=masque)
    r, e, c = 250 * x, 105 * x, t // 2
    boite = (c - r, c - r, c + r, c + r)
    voile = Image.new("RGBA", (t, t))
    ImageDraw.Draw(voile).arc(boite, 0, 360, fill=(255, 255, 255, 95), width=e)
    icone = Image.alpha_composite(icone, voile)
    d = ImageDraw.Draw(icone)
    d.arc(boite, 180, 450, fill=(255, 255, 255, 255), width=e)  # trois quarts, de 9 h à 6 h
    for angle in (180, 90):  # bouts arrondis
        a = math.radians(angle)
        px, py = c + (r - e / 2) * math.cos(a), c + (r - e / 2) * math.sin(a)
        d.ellipse((px - e / 2, py - e / 2, px + e / 2, py + e / 2), fill=(255, 255, 255, 255))
    icone.putalpha(ImageChops.multiply(icone.getchannel("A"), masque))
    return icone.resize((N, N), Image.LANCZOS)


def principal():
    ICI.mkdir(exist_ok=True)
    img = dessiner()
    img.save(ICI / "SaveSpace.png")
    img.save(ICI / "SaveSpace.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        jeu = ICI / "SaveSpace.iconset"
        jeu.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            img.resize((s, s), Image.LANCZOS).save(jeu / f"icon_{s}x{s}.png")
            img.resize((2 * s, 2 * s), Image.LANCZOS).save(jeu / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(ICI / "SaveSpace.icns")], check=True)
        shutil.rmtree(jeu)
    print("icônes :", ", ".join(sorted(p.name for p in ICI.iterdir())))


if __name__ == "__main__":
    principal()
