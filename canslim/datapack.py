"""Price files travel as one zip on a GitHub Release, not in git history.

data/prices holds ~2,400 parquet files that every scan rewrites (~150 MB). In git each scan added the whole
lot again, forever. Instead:

  publish()        (local, after the daily scan) zips data/prices/*.parquet and replaces the asset
                   `prices.zip` on the release `data-latest`. Each upload overwrites the last one, so
                   nothing accumulates. It also writes data/prices_version.txt (tracked in git).
  ensure_prices()  (cloud app at start-up) downloads and unpacks the zip when data/prices is empty or
                   its unpacked version differs from data/prices_version.txt in the deployed commit.

Upload auth: the GitHub login git already uses (Windows Credential Manager via `git credential fill`),
read at upload time only, never printed or saved. Download needs no auth (public repo).

    python -m canslim.datapack publish
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices"
VERSION_FILE = ROOT / "data" / "prices_version.txt"      # tracked: what the deployed commit expects
LOCAL_VERSION = PRICES / ".version"                     # untracked: what is unpacked here
REPO = "srijonroy/canslim-nse"
TAG = "data-latest"
ASSET = "prices.zip"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
API = f"https://api.github.com/repos/{REPO}"


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


# ---------------------------------------------------------------- cloud side

def ensure_prices(log=print) -> bool:
    """Make data/prices match data/prices_version.txt. Returns True if it downloaded."""
    want = _read(VERSION_FILE)
    have_files = any(PRICES.glob("*.parquet"))
    have = _read(LOCAL_VERSION)
    if have_files and (not want or not have or have == want):
        return False          # local machine (no marker yet) or already current: never overwrite local data
    PRICES.mkdir(parents=True, exist_ok=True)
    log(f"downloading price data ({want or 'latest'})...")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / ASSET
        with requests.get(DOWNLOAD_URL, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        with zipfile.ZipFile(tmp) as z:
            for name in z.namelist():                  # flat archive of *.parquet only; refuse anything else
                if "/" in name or "\\" in name or not name.endswith(".parquet"):
                    raise RuntimeError(f"unexpected entry in {ASSET}: {name}")
            z.extractall(PRICES)
            ver = z.comment.decode() or want
    LOCAL_VERSION.write_text(ver)
    log(f"price data ready: {ver}")
    return True


# ---------------------------------------------------------------- local side

def _token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, cwd=ROOT, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).stdout
    tok = next((l.split("=", 1)[1] for l in out.splitlines() if l.startswith("password=")), "")
    if not tok:
        raise RuntimeError("no GitHub credential stored for git (push once from this PC first)")
    return tok


def _release(h: dict) -> dict:
    r = requests.get(f"{API}/releases/tags/{TAG}", headers=h, timeout=30)
    if r.status_code == 404:
        r = requests.post(f"{API}/releases", headers=h, timeout=30, json={
            "tag_name": TAG, "name": "Data (latest)", "prerelease": True, "make_latest": "false",
            "body": "Price files for the tracker app, replaced after each scan. Not a software release."})
    r.raise_for_status()
    return r.json()


def publish(log=print) -> str:
    files = sorted(PRICES.glob("*.parquet"))
    if len(files) < 100:
        raise RuntimeError(f"only {len(files)} price files in {PRICES}; refusing to publish")
    ver = datetime.now().strftime("%Y-%m-%d %H:%M") + f" ({len(files)} files)"
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / ASSET
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:   # parquet is already compressed
            for f in files:
                z.write(f, f.name)
            z.comment = ver.encode()
        mb = tmp.stat().st_size / 1e6
        log(f"datapack: zipped {len(files)} files, {mb:.0f} MB in {time.time() - t0:.0f}s; uploading...")
        h = {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"}
        rel = _release(h)
        old = {a["name"]: a["id"] for a in rel.get("assets", [])}
        staging = "prices-upload.zip"        # upload first, swap after: a failed upload never leaves no data
        if staging in old:
            requests.delete(f"{API}/releases/assets/{old[staging]}", headers=h, timeout=30).raise_for_status()
        up = rel["upload_url"].split("{")[0]
        with open(tmp, "rb") as f:
            r = requests.post(f"{up}?name={staging}", headers={**h, "Content-Type": "application/zip"},
                              data=f, timeout=1800)
        r.raise_for_status()
        new_id = r.json()["id"]
        if ASSET in old:
            requests.delete(f"{API}/releases/assets/{old[ASSET]}", headers=h, timeout=30).raise_for_status()
        requests.patch(f"{API}/releases/assets/{new_id}", headers=h, timeout=30,
                       json={"name": ASSET}).raise_for_status()
    VERSION_FILE.write_text(ver + "\n")
    LOCAL_VERSION.write_text(ver)
    log(f"datapack: published {ASSET} ({mb:.0f} MB) in {time.time() - t0:.0f}s total -> {ver}")
    return ver


if __name__ == "__main__":
    if sys.argv[1:] == ["publish"]:
        publish(lambda m: print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m, flush=True))
    elif sys.argv[1:] == ["ensure"]:
        ensure_prices()
    else:
        sys.exit("usage: python -m canslim.datapack publish|ensure")
