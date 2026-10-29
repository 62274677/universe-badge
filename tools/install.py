"""Install the app on a badge over USB Disk Mode.

Needed once per badge, and again only if the loader (__init__.py) or ota.py
change; live/ code arrives over the air after that.

  1. Connect a USB-C data cable and double-tap RESET. A BADGER drive appears
     (RP2350 is the firmware bootloader drive; never copy there).
  2. python tools/install.py            (or --mount E:/ to pick the drive)
  3. Eject BADGER. The badge restarts into the menu; open "Universe Badge".
"""
import argparse
import glob
import pathlib
import shutil
import string
import sys

APP = "universe_badge"
SRC = pathlib.Path(__file__).resolve().parent.parent / "badge" / "apps" / APP


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

    dest = apps / APP
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=ignore)
    print("installed %s -> %s" % (SRC.name, dest))

    secrets = apps.parent / "secrets.py"
    text = secrets.read_text() if secrets.exists() else ""
    if 'WIFI_SSID = ""' in text or "WIFI_SSID" not in text:
        print("warning: set WIFI_SSID and WIFI_PASSWORD in %s, or the badge can't "
              "check for updates" % secrets)
    print("Now eject the drive; the badge restarts into the menu.")


if __name__ == "__main__":
    main()
