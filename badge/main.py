"""Badge bootloader: join WiFi, pull any new build from CI, run the app.

This file and ota.py are installed over USB (tools/flash.py) and never
updated over the air. If an OTA-installed app crashes, the loop at the
bottom keeps polling for a new build, so pushing a fix to main recovers
the badge without a cable.
"""
import sys
import time

import machine
import network

import ota

try:
    import wifi_config
except ImportError:
    wifi_config = None

UPDATE_URL = "https://62274677.github.io/universe-badge/"
CHECK_EVERY_S = 300

_wlan = network.WLAN(network.STA_IF)
_last_check = None


def connect_wifi(timeout_s=15):
    """Join the first known network in range. Returns True if online."""
    if _wlan.isconnected():
        return True
    if wifi_config is None:
        print("no wifi_config.py: staying offline")
        return False
    _wlan.active(True)
    visible = {s[0].decode() for s in _wlan.scan()}
    for ssid, password in wifi_config.NETWORKS:
        if ssid not in visible:
            continue
        print("joining", ssid)
        _wlan.connect(ssid, password)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if _wlan.isconnected():
                print("online", _wlan.ifconfig()[0])
                return True
            time.sleep(0.5)
        _wlan.disconnect()
    return False


def check_for_update(force=False):
    """Install a newly published build, then reboot into it.

    The app calls this from its main loop; it is a no-op until
    CHECK_EVERY_S has passed since the last check.
    """
    global _last_check
    now = time.time()
    if not force and _last_check is not None and now - _last_check < CHECK_EVERY_S:
        return
    _last_check = now
    if not connect_wifi():
        return
    try:
        version = ota.update(UPDATE_URL)
    except Exception as e:
        print("update failed:", repr(e))
        return
    if version:
        print("installed build", version, "- rebooting")
        machine.reset()


def show_error(message):
    print(message)
    try:
        import badger2040
    except ImportError:
        return
    d = badger2040.Badger2040()
    d.set_pen(15)
    d.clear()
    d.set_pen(0)
    d.set_font("bitmap8")
    d.text(message, 5, 5, badger2040.WIDTH - 10, 2)
    d.update()


def main():
    check_for_update(force=True)
    try:
        from app import main as app_main
        app_main.run(check_for_update)
        show_error("app exited; waiting for a new build")
    except Exception as e:
        sys.print_exception(e)
        show_error("app crashed: %r\nwaiting for a new build" % e)
    while True:
        time.sleep(30)
        check_for_update()


main()
