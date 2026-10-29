"""Install the apps on a badge over USB Disk Mode.

Needed once per badge, and again only if a loader (__init__.py), ota.py or
wifi_networks.py change; live/ code arrives over the air after that.

  1. Connect a USB-C data cable and double-tap RESET. A BADGER drive appears
     (RP2350 is the firmware bootloader drive; never copy there).
  2. python tools/install.py            (or --mount E:/ to pick the drive)
  3. Eject BADGER. The badge restarts into the menu.

Besides the apps it installs wifi_networks.py (saved WiFi networks, see that
file) and hooks two places in the badge's own code, each once, keeping a copy
of the original in .badge-app-backups/ on the drive:
  - main.py: load wifi_networks before any app runs, so every app can use them;
  - the menu: open the screensaver after 60 s idle or on UP + DOWN + BACK.
"""
import argparse
import datetime
import glob
import pathlib
import shutil
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ROOT / "badge" / "apps"
WIFI_NETWORKS = ROOT / "badge" / "wifi_networks.py"

MAIN_ANCHOR = '''    sparkle = None
    print("sparkle unavailable:", error)
'''
MAIN_HOOK = '''
# saved WiFi networks for every app (universe-badge tools/install.py)
try:
    __import__("/system/wifi_networks").install()
except Exception as error:  # noqa: BLE001
    print("wifi networks unavailable:", error)
'''

MENU_STATE_ANCHOR = '''FADE_STEP = 30
IDLE_MS = 600
fade = 0 if opening is None else 255
viewer = None
celebration = None
'''
MENU_STATE = '''FADE_STEP = 30
IDLE_MS = 600
SCREENSAVER = "/system/apps/screensaver"
SCREENSAVER_IDLE_MS = 60 * 1000
SCREENSAVER_KEYS = (BUTTON_UP, BUTTON_DOWN, BUTTON_BACK)
fade = 0 if opening is None else 255
viewer = None
celebration = None
last_input = badge.ticks


def screensaver_installed():
    try:
        os.stat(SCREENSAVER + "/__init__.py")
        return True
    except OSError:
        return False


has_screensaver = screensaver_installed()
'''
MENU_UPDATE_ANCHOR = '''def update():
    global fade, opening, viewer, celebration
'''
MENU_UPDATE = '''def update():
    global fade, opening, viewer, celebration, last_input

    if badge.pressed() or badge.held():
        last_input = badge.ticks
    if has_screensaver and opening is None:
        chord = all(badge.held(key) for key in SCREENSAVER_KEYS)
        if chord or badge.ticks - last_input >= SCREENSAVER_IDLE_MS:
            restore()
            return SCREENSAVER
'''


def candidates():
    if sys.platform == "win32":
        return ["%s:/" % letter for letter in string.ascii_uppercase]
    return ["/Volumes/BADGER"] + glob.glob("/media/*/BADGER") + glob.glob("/run/media/*/BADGER")


def find_apps_dir(mount):
    """The BADGER volume root holds apps/ (some builds: system/apps/)."""
    root = pathlib.Path(mount)
    for apps in (root / "apps", root / "system" / "apps"):
        if (apps / "menu").is_dir():
            return apps
    return None


def ignore(_dir, names):
    return [n for n in names if n.startswith(".") or n in ("__pycache__", "PREVIEW")]


def patch(path, marker, replacements, backups):
    """Apply (anchor, replacement) pairs once; returns a short status."""
    if not path.exists():
        return "skipped: %s not found" % path.name
    text = path.read_text()
    if marker in text:
        return "already hooked"
    for anchor, _ in replacements:
        if anchor not in text:
            return "skipped: %s doesn't match the expected firmware code" % path.name
    backups.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, backups / ("%s-%s-%s" % (path.parent.name, path.name, stamp)))
    for anchor, replacement in replacements:
        text = text.replace(anchor, replacement, 1)
    path.write_text(text)
    return "hooked"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mount", help="BADGER drive or folder (default: search)")
    args = p.parse_args()

    found = [a for a in map(find_apps_dir, [args.mount] if args.mount else candidates()) if a]
    if not found:
        sys.exit("No BADGER drive found. Double-tap RESET on the badge, wait for the "
                 "drive, then retry (or pass --mount).")
    if len(found) > 1:
        sys.exit("Several BADGER drives: %s. Pick one with --mount." % ", ".join(map(str, found)))
    apps = found[0]
    drive = apps.parent
    backups = drive / ".badge-app-backups"

    for src in sorted(d for d in APPS.iterdir() if (d / "__init__.py").exists()):
        dest = apps / src.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=ignore)
        print("installed %s -> %s" % (src.name, dest))

    shutil.copy2(WIFI_NETWORKS, drive / WIFI_NETWORKS.name)
    print("installed %s -> %s" % (WIFI_NETWORKS.name, drive))
    print("main.py:", patch(drive / "main.py", "wifi_networks",
                            [(MAIN_ANCHOR, MAIN_ANCHOR + MAIN_HOOK)], backups))
    print("menu:", patch(apps / "menu" / "__init__.py", "SCREENSAVER =",
                         [(MENU_STATE_ANCHOR, MENU_STATE), (MENU_UPDATE_ANCHOR, MENU_UPDATE)],
                         backups))

    secrets = drive / "secrets.py"
    text = secrets.read_text() if secrets.exists() else ""
    if "WIFI_NETWORKS" not in text and ('WIFI_SSID = ""' in text or "WIFI_SSID" not in text):
        print("warning: set WIFI_NETWORKS (or WIFI_SSID and WIFI_PASSWORD) in %s, or the "
              "badge can't check for updates" % secrets)
    print("Now eject the drive; the badge restarts into the menu.")


if __name__ == "__main__":
    main()
