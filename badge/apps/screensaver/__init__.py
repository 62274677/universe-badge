"""Loader for the screensaver: runs live/ and keeps it up to date over WiFi.

Works like universe_badge's loader (ota.py is an identical copy) and, like
it, is installed once over USB Disk Mode and never updated over the air. A
screensaver runs on battery for up to half an hour, so it checks for a new
build once per launch, a few seconds in, only with enough charge, and turns
the WiFi radio off again as soon as the check is done.
"""
import os
import sys

APP_DIR = "/system/apps/screensaver"
BUNDLED_DIR = APP_DIR + "/live"
INSTALL_DIR = "/ota/screensaver"
UPDATE_URL = "https://62274677.github.io/universe-badge/screensaver/"
CHECK_AFTER_MS = 5000      # let the first frames draw before the radio starts
CHECK_BUDGET_MS = 45000    # give up and save power if WiFi or Pages is slow
MIN_BATTERY = 25           # percent; skip the check below this unless on USB
NEVER_MS = 1 << 30

os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

try:
    __import__("/system/wifi_networks").install()
except Exception as e:  # missing or broken: fall back to WIFI_SSID in secrets.py
    print("[screensaver] saved wifi networks unavailable:", e)

import ota  # noqa: E402


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _battery_ok():
    try:
        if badge.usb_connected():
            return True
    except AttributeError:
        if badge.is_charging():
            return True
    try:
        return badge.battery_level() >= MIN_BATTERY
    except Exception:
        return True


def _radio_off():
    try:
        import wifi
        wifi.disconnect()
    except Exception as e:
        print("[screensaver] wifi off:", e)


# tools/preview adds this file so the simulator runs your local live/ code
# instead of downloading the published build.
PREVIEW = _exists(APP_DIR + "/PREVIEW")

updater = ota.Updater(UPDATE_URL, INSTALL_DIR, every_ms=NEVER_MS, retry_ms=NEVER_MS)
check_at = None if PREVIEW else badge.ticks + CHECK_AFTER_MS
check_until = None
app = None
crash = None


def _exit_app():
    on_exit = getattr(app, "on_exit", None)
    if on_exit:
        try:
            on_exit()
        except Exception as e:
            sys.print_exception(e)


def _load():
    """(Re)import the live code: the installed build if any, else the bundled copy."""
    global app, crash
    _exit_app()
    app = None
    crash = None
    for name in list(sys.modules):
        path = getattr(sys.modules[name], "__file__", "") or ""
        if name == "badge_app" or path.startswith(INSTALL_DIR) or path.startswith(BUNDLED_DIR):
            del sys.modules[name]

    installed = None if PREVIEW else ota.current_version(INSTALL_DIR)
    live = INSTALL_DIR if installed else BUNDLED_DIR
    ota.build = "preview" if PREVIEW else installed or "usb"
    for d in (INSTALL_DIR, BUNDLED_DIR):
        while d in sys.path:
            sys.path.remove(d)
    sys.path.insert(0, live)
    os.chdir(live)
    try:
        import badge_app
        app = badge_app
    except Exception as e:
        crash = e
        sys.print_exception(e)


def _check_for_update():
    """Drive the one update check of this launch, a step per frame."""
    global check_at, check_until
    now = badge.ticks
    if check_at is not None:
        if now < check_at:
            return
        check_at = None
        if not _battery_ok():
            updater.status = "battery low: skipped update check"
            return
        check_until = now + CHECK_BUDGET_MS
    if check_until is None:
        return
    updater.step(now)
    if updater.installed:
        updater.installed = False
        _load()
    if not updater.busy or now > check_until:
        if updater.busy:
            updater.status = "update check timed out"
        check_until = None
        _radio_off()
        print("[screensaver]", updater.status)


def _status_screen():
    screen.pen = color.rgb(13, 17, 23)
    screen.clear()
    screen.font = font.nope
    screen.pen = color.rgb(248, 81, 73) if crash else color.rgb(240, 246, 252)
    if crash:
        message = "screensaver crashed:\n%s: %s" % (type(crash).__name__, crash)
    else:
        message = "no screensaver installed yet"
    screen.text(message + "\n\n" + updater.status + "\n\nany button: back to menu",
                rect(4, 4, screen.width - 8, screen.height - 8))


def update():
    global app, crash
    _check_for_update()
    if app is None:
        _status_screen()
        return True if badge.pressed() else None
    try:
        return app.update()
    except Exception as e:
        sys.print_exception(e)
        _exit_app()  # restores the backlight and case lights
        crash = e
        app = None
        return None


def on_exit():
    _exit_app()
    if check_until is not None:
        _radio_off()


_load()
run(update)
