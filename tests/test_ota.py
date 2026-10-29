"""End-to-end OTA: build_manifest publishes a site, ota.update installs it."""
import json
import shutil

import pytest

import build_manifest
import ota

BASE = "https://example.test/badge/"


@pytest.fixture
def site(tmp_path, monkeypatch):
    """publish({rel: text}, version) builds a fake Pages site that ota reads."""
    src, out = tmp_path / "src", tmp_path / "site"

    def publish(files, version):
        shutil.rmtree(src, ignore_errors=True)
        for rel, text in files.items():
            path = src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        build_manifest.build(src, out, version)

    def chunks(url):
        assert url.startswith(BASE)
        rel = url[len(BASE):].split("?")[0]
        publish.fetched.append(rel)
        data = (out / rel).read_bytes()
        for i in range(0, len(data), 7):
            yield data[i:i + 7]

    monkeypatch.setattr(ota, "_chunks", chunks)
    publish.fetched = []
    publish.out = out
    return publish


@pytest.fixture
def badge(tmp_path):
    root = tmp_path / "badge"
    root.mkdir()
    return root


def install(badge):
    return ota.update(BASE, root=str(badge) + "/")


def test_fresh_install(site, badge):
    site({"app/main.py": "print(1)", "app/lib/util.py": "x = 2"}, "1-aaa")
    assert install(badge) == "1-aaa"
    assert (badge / "app/main.py").read_text() == "print(1)"
    assert (badge / "app/lib/util.py").read_text() == "x = 2"
    assert ota.read_state(str(badge) + "/")["version"] == "1-aaa"


def test_same_version_fetches_only_the_manifest(site, badge):
    site({"app/main.py": "print(1)"}, "1-aaa")
    install(badge)
    site.fetched.clear()
    assert install(badge) is None
    assert site.fetched == ["manifest.json"]


def test_downloads_only_changed_files_and_deletes_removed_ones(site, badge):
    site({"app/main.py": "print(1)", "app/keep.py": "k", "app/old.py": "o"}, "1-aaa")
    install(badge)
    site({"app/main.py": "print(2)", "app/keep.py": "k"}, "2-bbb")
    site.fetched.clear()
    assert install(badge) == "2-bbb"
    assert site.fetched == ["manifest.json", "app/main.py"]
    assert (badge / "app/main.py").read_text() == "print(2)"
    assert not (badge / "app/old.py").exists()


def test_checksum_mismatch_leaves_installed_build_alone(site, badge):
    site({"app/main.py": "print(1)"}, "1-aaa")
    install(badge)
    site({"app/main.py": "print(2)"}, "2-bbb")
    (site.out / "app/main.py").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        install(badge)
    assert (badge / "app/main.py").read_text() == "print(1)"
    assert not (badge / "app/main.py.new").exists()
    assert ota.read_state(str(badge) + "/")["version"] == "1-aaa"


def test_refuses_paths_outside_app(site, badge):
    site({"app/main.py": "print(1)"}, "1-aaa")
    manifest = json.loads((site.out / "manifest.json").read_text())
    manifest["files"]["main.py"] = manifest["files"].pop("app/main.py")
    (site.out / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="outside app/"):
        install(badge)
    assert list(badge.iterdir()) == []
