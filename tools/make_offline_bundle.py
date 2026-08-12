#!/usr/bin/env python3
"""Rebuild `vendor/python/` -- the ready-to-run Windows runtime in this repo.

WHY THIS EXISTS
---------------
The bench PC is offline AND its only Python is a 2.x that must not be touched.
So the repo ships its own interpreter: an unpacked Windows *embeddable* Python
with our dependencies already installed inside it.  Nothing is installed on the
bench, nothing is registered, the system Python 2 never learns we exist -- the
folder is copied over and `start.bat` runs.

That bundle is checked in, so normally you do NOT need this script.  Run it
when you bump `app/requirements.txt`, move to another Python patch level, or need
the 32-bit build:

    python3 tools/make_offline_bundle.py                    # defaults below
    python3 tools/make_offline_bundle.py --python 3.8.10 --arch amd64
    python3 tools/make_offline_bundle.py --embed-zip ~/Downloads/py.zip

Run it on a machine WITH internet (any OS -- the wheels are fetched for the
Windows target, not for the host).  Commit the result.

Python 3.8 is the default on purpose: it is the last release that still
supports Windows 7, and the bench is old.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-{arch}.zip"

# `._pth` lines, resolved relative to the folder holding python.exe.
#   Lib\site-packages -- or the embeddable simply does not see what we install;
#   ..\..             -- the repo root.  A `._pth` puts the interpreter in
#                        isolated mode, which does NOT prepend the script's
#                        directory, so without this line every `import
#                        settings` / `import config` fails (bench, 2026-07-28);
#   import site       -- or the .pth files inside site-packages never run.
PTH_TEMPLATE = ("python{tag}.zip\n.\nLib\\site-packages\n..\\..\n"
                "\nimport site\n")


def log(msg: str) -> None:
    print("[bundle] " + msg)


def fetch_embeddable(version: str, arch: str, cache: str) -> str:
    """Return a local path to the embeddable zip, downloading it if needed."""
    url = EMBED_URL.format(v=version, arch=arch)
    dest = os.path.join(cache, os.path.basename(url))
    if os.path.exists(dest):
        log("using cached %s" % dest)
        return dest
    os.makedirs(cache, exist_ok=True)
    log("downloading %s" % url)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    return dest


def install_deps(site_packages: str, requirements: str, tag: str, arch: str) -> None:
    """pip-install the requirements FOR WINDOWS into `site_packages`.

    `--platform` + `--only-binary=:all:` is what lets this run on macOS/Linux
    and still produce win_amd64 artefacts (the playwright wheel carries the
    node driver, so the host's own wheels would be useless on the bench).
    """
    platform_tag = "win_amd64" if arch == "amd64" else "win32"
    cmd = [
        sys.executable, "-m", "pip", "install",
        "-r", requirements,
        "--target", site_packages,
        "--platform", platform_tag,
        "--python-version", tag,
        "--only-binary=:all:",
        "--upgrade",
    ]
    log("pip install --platform %s --python-version %s" % (platform_tag, tag))
    subprocess.check_call(cmd)


def prune(site_packages: str) -> None:
    """Drop what a cross-platform `--target` install leaves behind.

    `bin/` holds POSIX console scripts (we never call the playwright CLI) and
    `include/` is empty headers; both are dead weight in a committed bundle.
    """
    for junk in ("bin", "include"):
        path = os.path.join(site_packages, junk)
        if os.path.isdir(path):
            shutil.rmtree(path)
            log("pruned %s/" % junk)
    for root, dirs, _files in os.walk(site_packages):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d))
                dirs.remove(d)
    # The RECORDs still point at the console scripts we just deleted, and their
    # hash embeds this build machine's interpreter path -- which would make two
    # builds of the same versions differ for no reason.  Drop those lines so a
    # rebuild is byte-identical and the RECORD stops naming missing files.
    for entry in sorted(os.listdir(site_packages)):
        record = os.path.join(site_packages, entry, "RECORD")
        if not entry.endswith(".dist-info") or not os.path.isfile(record):
            continue
        with open(record, encoding="utf-8") as fh:
            lines = fh.readlines()
        kept = [ln for ln in lines
                if not ln.startswith(("../../bin/", "../../include/"))]
        if len(kept) != len(lines):
            with open(record, "w", encoding="utf-8", newline="") as fh:
                fh.writelines(kept)
            log("cleaned %s/RECORD" % entry)


def folder_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default="3.8.10",
                    help="CPython version to embed (default: %(default)s)")
    ap.add_argument("--arch", default="amd64", choices=("amd64", "win32"),
                    help="Windows architecture of the BENCH (default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(REPO, "vendor", "python"),
                    help="where to write the runtime (default: vendor/python)")
    ap.add_argument("--requirements", default=os.path.join(REPO, "app", "requirements.txt"))
    ap.add_argument("--embed-zip", default=None,
                    help="use this already-downloaded embeddable zip instead "
                         "of fetching one (for a half-offline build machine)")
    ap.add_argument("--cache", default=os.path.join(REPO, ".bundle-cache"),
                    help="download cache dir (default: %(default)s, git-ignored)")
    args = ap.parse_args()

    major, minor = args.python.split(".")[:2]
    tag = major + minor  # "38" -- both the zip name and pip's --python-version

    zip_path = args.embed_zip or fetch_embeddable(args.python, args.arch, args.cache)

    if os.path.isdir(args.out):
        log("clearing %s" % args.out)
        shutil.rmtree(args.out)
    os.makedirs(args.out)

    log("unpacking %s" % os.path.basename(zip_path))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(args.out)

    pth = os.path.join(args.out, "python%s._pth" % tag)
    with open(pth, "w", encoding="ascii") as fh:
        fh.write(PTH_TEMPLATE.format(tag=tag))
    log("wrote %s" % os.path.basename(pth))

    site_packages = os.path.join(args.out, "Lib", "site-packages")
    install_deps(site_packages, args.requirements, tag, args.arch)
    prune(site_packages)

    size_mb = folder_size(args.out) / (1024.0 * 1024.0)
    log("done: %s (%.0f MB)" % (args.out, size_mb))
    print()
    print("Next:")
    print("  1) sanity-check on any Windows box, or on the bench itself:")
    print("       vendor\\python\\python.exe -c \"import playwright.sync_api, yaml; print('ok')\"")
    print("  2) commit vendor/ so the next person only has to download the repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
