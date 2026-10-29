"""Saved WiFi networks for every app on the badge.

The firmware's wifi.connect() only knows WIFI_SSID / WIFI_PASSWORD. List more
networks in secrets.py, most preferred first:

    WIFI_NETWORKS = [
        ("Home", "home password"),
        ("Phone hotspot", "hotspot password"),
    ]

install() wraps wifi.connect() so any call without an ssid picks a saved
network instead: the first in the list that is in range with a usable signal,
then weaker ones from strongest to weakest, then those the scan didn't see
(hidden networks). If one doesn't come up within SWITCH_AFTER_MS, it moves on
to the next. WIFI_SSID (what the Settings app edits) is tried after the list.

Installed to /system/wifi_networks.py by tools/install.py, which also hooks it
into the badge's main.py so it applies before any app runs.
"""
import time

SWITCH_AFTER_MS = 15000
USABLE_RSSI = -80  # dBm; weaker than this only gets used if nothing better is around

_wifi = None
_original = None
_candidates = None
_index = 0
_started = None


def _ticks():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def _elapsed(since):
    now = _ticks()
    return time.ticks_diff(now, since) if hasattr(time, "ticks_diff") else now - since


def saved(secrets=None):
    """[(ssid, password)] from secrets.py, in preference order, without duplicates."""
    if secrets is None:
        try:
            import secrets
        except ImportError:
            return []
    entries = list(getattr(secrets, "WIFI_NETWORKS", None) or [])
    entries.append((getattr(secrets, "WIFI_SSID", ""), getattr(secrets, "WIFI_PASSWORD", "")))
    networks = []
    for entry in entries:
        if isinstance(entry, str):
            entry = (entry, "")
        try:
            ssid = entry[0]
            password = entry[1] if len(entry) > 1 else ""
        except (TypeError, IndexError):
            continue
        if ssid and ssid not in [name for name, _ in networks]:
            networks.append((ssid, password or ""))
    return networks


def rank(networks, scan):
    """Order saved networks by preference, given WLAN.scan() results.

    In range with a usable signal: list order. Then weak ones, strongest first.
    Then everything the scan didn't see, in list order.
    """
    strongest = {}
    for row in scan:
        name = row[0].decode() if isinstance(row[0], bytes) else row[0]
        rssi = row[3]
        if name not in strongest or rssi > strongest[name]:
            strongest[name] = rssi
    usable = [n for n in networks if strongest.get(n[0], -999) >= USABLE_RSSI]
    weak = [n for n in networks if n[0] in strongest and n not in usable]
    weak.sort(key=lambda n: -strongest[n[0]])
    unseen = [n for n in networks if n[0] not in strongest]
    return usable + weak + unseen


def _scan():
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        return wlan.scan()
    except Exception as e:
        print("[wifi] scan failed:", e)
        return []


def _connect(*args, **kwargs):
    global _candidates, _index, _started
    if args or "ssid" in kwargs or "psk" in kwargs:
        return _original(*args, **kwargs)
    if _candidates is None:
        networks = saved()
        _candidates = rank(networks, _scan()) if len(networks) > 1 else networks
        _index = 0
        _started = None
        if _candidates:
            print("[wifi] trying", ", ".join(name for name, _ in _candidates))
    if not _candidates:
        return _original(**kwargs)  # the firmware explains what's missing
    if _started is None:
        _started = _ticks()
    ssid, password = _candidates[_index]
    if _original(ssid, password, **kwargs):
        _started = None  # the next attempt (after a disconnect) gets a fresh timer
        return True
    if len(_candidates) > 1 and _elapsed(_started) > SWITCH_AFTER_MS:
        _wifi.disconnect()
        _index = (_index + 1) % len(_candidates)
        _started = _ticks()
        print("[wifi] no luck with %s, trying %s" % (ssid, _candidates[_index][0]))
    return False


def install():
    """Wrap wifi.connect(); safe to call more than once."""
    global _wifi, _original
    import wifi
    if wifi.connect is _connect:
        return
    _wifi = wifi
    _original = wifi.connect
    wifi.connect = _connect
