"""Build the site CI publishes to GitHub Pages: each app's live/ files plus its manifest.json.

    python tools/build_manifest.py --version 12-abc1234 --out dist

Every app under badge/apps with a live/ folder is published. universe_badge goes at the
site root (where its installed loaders already look); the others under <app>/, e.g.
screensaver/manifest.json. --src builds a single folder instead.
"""
import argparse
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ROOT / "badge" / "apps"
ROOT_APP = "universe_badge"


def build(src, out, version, clean=True):
    src, out = pathlib.Path(src), pathlib.Path(out)
    if clean and out.exists():
        shutil.rmtree(out)
    files = {}
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src).as_posix()
        # The badge refuses hidden paths (.DS_Store would block every update).
        hidden = any(part.startswith(".") for part in rel.split("/"))
        if path.is_dir() or hidden or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    manifest = {"version": version, "files": files}
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def build_site(out, version, apps=APPS):
    """Publish every app's live/ folder; returns {app: manifest}."""
    out = pathlib.Path(out)
    if out.exists():
        shutil.rmtree(out)
    manifests = {}
    for live in sorted(pathlib.Path(apps).glob("*/live")):
        app = live.parent.name
        dest = out if app == ROOT_APP else out / app
        manifests[app] = build(live, dest, version, clean=False)
    return manifests


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", required=True)
    p.add_argument("--src", help="build just this folder (default: every app's live/)")
    p.add_argument("--out", default=ROOT / "dist")
    args = p.parse_args()
    if args.src:
        manifest = build(args.src, args.out, args.version)
        print("build %s: %d files" % (manifest["version"], len(manifest["files"])))
        return
    for app, manifest in build_site(args.out, args.version).items():
        print("%s build %s: %d files" % (app, manifest["version"], len(manifest["files"])))


if __name__ == "__main__":
    main()
