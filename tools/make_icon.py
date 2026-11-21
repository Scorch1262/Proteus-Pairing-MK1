"""Erzeugt assets/icon.png, icon.ico und icon.icns (Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent.parent / "assets"
out.mkdir(exist_ok=True)
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=200, fill=(17, 22, 27, 255), outline=(46, 57, 68, 255), width=16)
amber, teal = (245, 165, 36, 255), (46, 196, 182, 255)
# zwei Module
d.rounded_rectangle((170, 330, 420, 700), radius=40, outline=amber, width=40)
d.rounded_rectangle((604, 330, 854, 700), radius=40, outline=teal, width=40)
# Verbindung
for x in (480, 502, 524):
    d.ellipse((x, 505, x + 20, 525), fill=(211, 218, 225, 255))
d.polygon([(552, 470), (590, 515), (552, 560)], fill=teal)
d.polygon([(472, 470), (434, 515), (472, 560)], fill=amber)
img.save(out / "icon.png")
img.resize((256, 256), Image.LANCZOS).save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(out / "icon.icns")
print("Icons erzeugt in", out)
