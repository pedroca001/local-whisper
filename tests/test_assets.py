from localwhisper.assets import app_icon_paths, tray_icon_path


def test_app_icon_paths_include_available_sizes():
    names = {path.name for path in app_icon_paths()}

    assert {"icon.png", "128x128@2x.png", "128x128.png", "64x64.png", "32x32.png"} <= names


def test_tray_icon_path_picks_theme_variant():
    assert tray_icon_path("ready", dark_taskbar=True).name == "Ready-1.png"
    assert tray_icon_path("ready", dark_taskbar=False).name == "Ready.png"
