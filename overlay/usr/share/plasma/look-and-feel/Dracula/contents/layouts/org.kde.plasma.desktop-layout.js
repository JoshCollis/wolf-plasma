// This is the fresh global-theme layout, not a per-login reset script.
var panel = new Panel;
panel.location = "bottom";
panel.height = 44;
panel.addWidget("org.kde.plasma.kickoff");
panel.addWidget("org.kde.plasma.icontasks");
panel.addWidget("org.kde.plasma.systemtray");
panel.addWidget("org.kde.plasma.digitalclock");
for (var i = 0; i < screenCount; ++i) {
    var desktop = desktopForScreen(i);
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig("Image", "file:///usr/share/wallpapers/WolfPlasma/contents/images/1920x1080.svg");
}
