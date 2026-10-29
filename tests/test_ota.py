"""End-to-end OTA: build_manifest publishes a site, ota.Updater installs it
one polled step at a time, the way the badge's frame loop drives it."""
import json
import shutil

import pytest

import build_manifest
import ota
from conftest import net

BASE = "https://example.test/badge/"
EVERY = ota.Updater(BASE, "").every_ms


@pytest.fixture
def site(tmp_path, monkeypatch):
    """publish({rel: text}, version) builds a fake Pages site the fake fetch serves."""
    src, out = tmp_path / "src", tmp_path / "site"
    net.reset()
    monkeypatch.setattr(ota, "_wifi_configured", lambda: True)

    def serve(url):
        assert url.startswith(BASE)
        return (out / url[len(BASE):].split("?")[0]).read_bytes()

    def publish(files, version):
        shutil.rmtree(src, ignore_errors=True)
        src.mkdir(parents=True)
        for rel, text in files.items():
            path = src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        build_manifest.build(src, out, version)

    net.serve = serve
    publish.out = out
    return publish


@pytest.fixture
def badge(tmp_path):
    """The install directory; the updater creates it on first use."""
    return tmp_path / "ota" / "universe_badge"


class Clock:
    now = 0


def check(updater, max_steps=200):
    """Trigger a check, then step until the updater goes idle again."""
    Clock.now += EVERY + 1
    net.fetched.clear()
    for _ in range(max_steps):
        updater.step(Clock.now)
        Clock.now += 16
        if not updater.busy:
            return updater.status
    raise AssertionError("updater never went idle: " + updater.status)


def fetched():
    return [url[len(BASE):].split("?")[0] for url in net.fetched]


def make(badge):
    return ota.Updater(BASE, badge.as_posix())


def test_fresh_install(site, badge):
    site({"badge_app.py": "print(1)", "assets/a.txt": "x"}, "1-aaa")
    u = make(badge)
    assert check(u) == "installed build 1-aaa"
    assert u.installed
    assert (badge / "badge_app.py").read_text() == "print(1)"
    assert (badge / "assets/a.txt").read_text() == "x"
    assert ota.current_version(badge.as_posix()) == "1-aaa"
    assert not list(badge.glob("**/*.new")) and not (badge / ".manifest.tmp").exists()


def test_each_step_starts_at_most_one_download(site, badge):
    site({"a.py": "a", "b.py": "b", "c.py": "c"}, "1-aaa")
    u = make(badge)
    Clock.now += EVERY + 1
    net.fetched.clear()
    seen = 0
    while True:
        u.step(Clock.now)
        Clock.now += 16
        assert len(net.fetched) - seen <= 1
        seen = len(net.fetched)
        if not u.busy:
            break
    assert sorted(fetched()) == ["a.py", "b.py", "c.py", "manifest.json"]


def test_same_version_fetches_only_the_manifest(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    u = make(badge)
    check(u)
    u.installed = False
    assert check(u) == "up to date"
    assert fetched() == ["manifest.json"]
    assert not u.installed


def test_new_version_with_identical_files_needs_no_reload(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    u = make(badge)
    check(u)
    u.installed = False
    site({"badge_app.py": "print(1)"}, "2-bbb")
    assert check(u) == "up to date: 2-bbb"
    assert fetched() == ["manifest.json"]
    assert not u.installed
    assert ota.current_version(badge.as_posix()) == "2-bbb"


def test_downloads_only_changed_files_and_deletes_removed_ones(site, badge):
    site({"badge_app.py": "print(1)", "keep.py": "k", "old.py": "o"}, "1-aaa")
    u = make(badge)
    check(u)
    site({"badge_app.py": "print(2)", "keep.py": "k"}, "2-bbb")
    assert check(u) == "installed build 2-bbb"
    assert fetched() == ["manifest.json", "badge_app.py"]
    assert (badge / "badge_app.py").read_text() == "print(2)"
    assert not (badge / "old.py").exists()


def test_checksum_mismatch_leaves_installed_build_alone(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    u = make(badge)
    check(u)
    u.installed = False
    site({"badge_app.py": "print(2)"}, "2-bbb")
    (site.out / "badge_app.py").write_text("tampered")
    assert check(u).startswith("update failed: checksum mismatch")
    assert not u.installed
    assert (badge / "badge_app.py").read_text() == "print(1)"
    assert not (badge / "badge_app.py.new").exists()
    assert ota.current_version(badge.as_posix()) == "1-aaa"


def test_retries_sooner_after_a_failure(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    (site.out / "badge_app.py").unlink()
    u = make(badge)
    assert check(u) == "update failed: download failed: HTTP 404"
    net.fetched.clear()
    u.step(Clock.now + u.retry_ms + 1)
    assert u.busy  # retrying well before the next 5-minute check


def test_refuses_paths_outside_install_dir(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    manifest = json.loads((site.out / "manifest.json").read_text())
    manifest["files"]["../../system/main.py"] = manifest["files"].pop("badge_app.py")
    (site.out / "manifest.json").write_text(json.dumps(manifest))
    assert check(make(badge)).startswith("update failed: bad path in manifest")
    assert ota.current_version(badge.as_posix()) is None


def test_waits_for_wifi_then_gives_up(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    net.connects_after = 10**9
    assert check(make(badge), max_steps=5000) == "update failed: wifi: no AP found"
    assert net.fetched == []


def test_slow_wifi_still_installs(site, badge):
    site({"badge_app.py": "print(1)"}, "1-aaa")
    net.connects_after = 50
    assert check(make(badge)) == "installed build 1-aaa"


def test_no_wifi_configured(site, badge, monkeypatch):
    monkeypatch.setattr(ota, "_wifi_configured", lambda: False)
    u = make(badge)
    u.step(EVERY + 1)
    assert not u.busy
    assert u.status == "no WIFI_SSID in /system/secrets.py"
    assert net.fetched == []


def test_build_skips_hidden_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/badge_app.py").write_text("x")
    (tmp_path / "src/.DS_Store").write_text("junk")
    manifest = build_manifest.build(tmp_path / "src", tmp_path / "out", "1")
    assert list(manifest["files"]) == ["badge_app.py"]
