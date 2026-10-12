"""Extract only the required pinned theme assets; never execute upstream installers."""
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

archive, destination = sys.argv[1:]
out = Path(destination)
with tempfile.TemporaryDirectory() as work:
    root = Path(work)
    with tarfile.open(archive) as tar:
        wanted = ("gtk-3.0/", "gtk-4.0/", "assets/", "kde/kvantum/Dracula-purple/",
                  "kde/plasma/desktoptheme/Dracula/", "kde/plasma/look-and-feel/Plasma6/Dracula/",
                  "kde/aurorae/Dracula/")
        for member in tar:
            relative = member.name.split("/", 1)[-1]
            if relative.startswith(wanted) or relative in ("LICENSE", "index.theme") or relative.endswith(".colors"):
                tar.extract(member, root, filter="data")
    src = next(root.iterdir())
    for source, target in (
        ("gtk-3.0", "themes/Dracula/gtk-3.0"),
        ("gtk-4.0", "themes/Dracula/gtk-4.0"),
        ("assets", "themes/Dracula/assets"),
        ("kde/aurorae/Dracula", "aurorae/themes/Dracula"),
        ("kde/kvantum/Dracula-purple", "Kvantum/Dracula-purple"),
        ("kde/plasma/desktoptheme/Dracula", "plasma/desktoptheme/Dracula"),
        ("kde/plasma/look-and-feel/Plasma6/Dracula", "plasma/look-and-feel/Dracula"),
    ):
        shutil.copytree(src / source, out / target)
    shutil.copy2(src / "index.theme", out / "themes/Dracula/index.theme")
    (out / "color-schemes").mkdir(parents=True)
    for name in ("Dracula.colors", "DraculaPurple.colors"):
        source = next(src.rglob(name))
        shutil.copy2(source, out / "color-schemes" / name)
    (out / "doc/wolf-plasma/dracula").mkdir(parents=True)
    shutil.copy2(src / "LICENSE", out / "doc/wolf-plasma/dracula/LICENSE")

metadata = out / "plasma/look-and-feel/Dracula/metadata.json"
data = json.loads(metadata.read_text())
data.pop("X-KPackage-Dependencies", None)
metadata.write_text(json.dumps(data, indent=4) + "\n")
# Offline equivalents, including when reselected in Settings.
defaults = out / "plasma/look-and-feel/Dracula/contents/defaults"
text = defaults.read_text().replace("ColorScheme=Dracula", "ColorScheme=DraculaPurple")
text = text.replace("Theme=candy-icons", "Theme=Papirus-Dark")
text = text.replace("cursorTheme=Dracula-cursors", "cursorTheme=breeze_cursors")
defaults.write_text(text)
