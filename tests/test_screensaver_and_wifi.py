"""The screensaver's OTA wiring, the multi-app site layout, and saved WiFi networks."""
import json
import pathlib
import sys
import types

import pytest

import build_manifest
import wifi_networks

APPS = pathlib.Path(__file__).resolve().parent.parent / "badge" / "apps"


def test_every_ota_app_ships_the_same_updater():
    # ota.py is never updated over the air, so a fix must land in every copy at once.
    copies = {p.parent.name: p.read_bytes() for p in APPS.glob("*/ota.py")}
    assert {"universe_badge", "screensaver"} <= set(copies)
    assert len(set(copies.values())) == 1, "ota.py differs between %s" % sorted(copies)


def test_loader_urls_match_where_the_site_publishes_them():
    for app in ("universe_badge", "screensaver"):
        loader = (APPS / app / "__init__.py").read_text()
        suffix = "" if app == build_manifest.ROOT_APP else app + "/"
        assert 'UPDATE_URL = "https://62274677.github.io/universe-badge/%s"' % suffix in loader
        assert 'INSTALL_DIR = "/ota/%s"' % app in loader


def test_site_puts_universe_badge_at_the_root_and_others_in_folders(tmp_path):
    for app, name in (("universe_badge", "badge_app.py"), ("screensaver", "badge_app.py")):
        live = tmp_path / "apps" / app / "live"
        live.mkdir(parents=True)
        (live / name).write_text("# " + app)
    (tmp_path / "apps" / "menu").mkdir()  # no live/: not published
    out = tmp_path / "site"
    manifests = build_manifest.build_site(out, "7-abc", apps=tmp_path / "apps")
    assert sorted(manifests) == ["screensaver", "universe_badge"]
    assert (out / "badge_app.py").read_text() == "# universe_badge"
    assert (out / "screensaver" / "badge_app.py").read_text() == "# screensaver"
    root = json.loads((out / "manifest.json").read_text())
    assert list(root["files"]) == ["badge_app.py"]  # the root build ignores app folders
    assert json.loads((out / "screensaver" / "manifest.json").read_text())["version"] == "7-abc"


def secrets(networks=None, ssid="", password=""):
    return types.SimpleNamespace(WIFI_NETWORKS=networks, WIFI_SSID=ssid, WIFI_PASSWORD=password)


def test_saved_lists_networks_in_order_then_the_settings_one():
    s = secrets([("Home", "h"), ("Phone", "p"), "Open"], ssid="Venue", password="v")
    assert wifi_networks.saved(s) == [("Home", "h"), ("Phone", "p"), ("Open", ""), ("Venue", "v")]


def test_saved_skips_duplicates_blanks_and_junk():
    s = secrets([("Home", "h"), ("", "x"), 42, ("Home", "other")], ssid="Home", password="h")
    assert wifi_networks.saved(s) == [("Home", "h")]
    assert wifi_networks.saved(secrets()) == []


def scan(*rows):
    return [(name.encode(), b"bssid", 6, rssi, 3, False) for name, rssi in rows]


def test_rank_prefers_list_order_among_usable_networks():
    saved = [("Home", "h"), ("Phone", "p"), ("Venue", "v")]
    found = scan(("Venue", -40), ("Phone", -60), ("Home", -70), ("Home", -50))
    assert [n for n, _ in wifi_networks.rank(saved, found)] == ["Home", "Phone", "Venue"]


def test_rank_puts_weak_networks_after_usable_ones_strongest_first():
    saved = [("Home", "h"), ("Phone", "p"), ("Venue", "v"), ("Hidden", "x")]
    found = scan(("Home", -88), ("Phone", -83), ("Venue", -55))
    assert [n for n, _ in wifi_networks.rank(saved, found)] == ["Venue", "Phone", "Home", "Hidden"]


class FakeWifi:
    def __init__(self, works):
        self.works = works  # ssids that connect
        self.calls = []
        self.current = None

    def connect(self, ssid=None, psk=None, **kwargs):
        if self.current is None:
            self.current = ssid
        self.calls.append((self.current, kwargs))
        return self.current in self.works

    def disconnect(self):
        self.current = None


@pytest.fixture
def wifi(monkeypatch):
    def make(networks, visible, works):
        fake = FakeWifi(works)
        monkeypatch.setitem(sys.modules, "wifi", fake)
        monkeypatch.setitem(sys.modules, "secrets", secrets(networks))
        monkeypatch.setattr(wifi_networks, "_scan", lambda: scan(*visible))
        monkeypatch.setattr(wifi_networks, "_candidates", None)
        monkeypatch.setattr(wifi_networks, "_started", None)
        clock = types.SimpleNamespace(now=0)
        monkeypatch.setattr(wifi_networks, "_ticks", lambda: clock.now)
        monkeypatch.setattr(wifi_networks, "_elapsed", lambda since: clock.now - since)
        wifi_networks.install()
        wifi_networks.install()  # twice is harmless
        fake.clock = clock
        return fake
    return make


def test_connect_uses_the_preferred_network_in_range(wifi):
    fake = wifi([("Home", "h"), ("Phone", "p")], [("Phone", -50)], works={"Phone"})
    assert fake.connect(timeout=10) is True
    assert fake.calls == [("Phone", {"timeout": 10})]


def test_connect_moves_on_when_a_network_never_comes_up(wifi):
    fake = wifi([("Home", "h"), ("Phone", "p")], [("Home", -50), ("Phone", -60)],
                works={"Phone"})
    assert fake.connect() is False
    fake.clock.now = wifi_networks.SWITCH_AFTER_MS + 1
    assert fake.connect() is False  # gives up on Home, starts Phone
    assert fake.connect() is True
    assert [ssid for ssid, _ in fake.calls] == ["Home", "Home", "Phone"]


def test_explicit_ssid_bypasses_the_saved_list(wifi):
    fake = wifi([("Home", "h"), ("Phone", "p")], [], works={"Cafe"})
    assert fake.connect("Cafe", "c") is True
    assert fake.calls == [("Cafe", {})]
