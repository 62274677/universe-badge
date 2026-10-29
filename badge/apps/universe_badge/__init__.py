"""Loader: runs the live/ code and keeps it up to date over WiFi.

Installed once over USB Disk Mode (tools/install.py) and, like ota.py, never
updated over the air. CI publishes live/ to GitHub Pages on each push to main;
the updater downloads it to INSTALL_DIR and the loader swaps it in while the
app is open, no restart needed. If the live code crashes, the error stays on
screen and the updater keeps checking, so pushing a fix recovers the badge.
"""
import os
import sys

APP_DIR = "/system/apps/universe_badge"
BUNDLED_DIR = APP_DIR + "/live"
INSTALL_DIR = "/ota/universe_badge"
UPDATE_URL = "https://62274677.github.io/universe-badge/"

os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import ota  # noqa: E402


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


# tools/preview adds this file so the simulator runs your local live/ code
# instead of downloading the published build.
PREVIEW = _exists(APP_DIR + "/PREVIEW")

updater = ota.Updater(UPDATE_URL, INSTALL_DIR)
if PREVIEW:
    updater.status = "preview: running local code, not checking for updates"
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


def _status_screen():
    screen.pen = color.rgb(13, 17, 23)
    screen.clear()
    screen.font = font.nope
    screen.pen = color.rgb(248, 81, 73) if crash else color.rgb(240, 246, 252)
    if crash:
        message = "app crashed:\n%s: %s" % (type(crash).__name__, crash)
    else:
        message = "no app installed yet"
    screen.text(message + "\n\n" + updater.status,
                rect(4, 4, screen.width - 8, screen.height - 8))


def update():
    global app, crash
    if not PREVIEW:
        updater.step(badge.ticks)
        if updater.installed:
            updater.installed = False
            _load()
    if app is None:
        _status_screen()
        return None
    try:
        result = app.update()
    except Exception as e:
        sys.print_exception(e)
        crash = e
        app = None
        return None
    if updater.busy:  # a small dot while a check or download is in flight
        screen.pen = color.rgb(63, 185, 80)
        screen.shape(shape.circle(screen.width - 4, 4, 2))
    return result


def on_exit():
    _exit_app()


_load()
run(update)
