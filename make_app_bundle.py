"""Copy the tracker app plus a data snapshot into a small folder for Streamlit Community Cloud.

usage: python make_app_bundle.py [out_dir]     (default C:\\Project\\canslim-app)
Then commit + push that folder's own git repo; the cloud app redeploys on push.
Read-only snapshot: anything typed into the cloud app is lost when it restarts.
"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "canslim-app"

FILES = ["tracker_app.py", "canslim/db.py", "canslim/holdings.py", "canslim/paper.py", "canslim/autobrief.py",
         "canslim/docs.py", "data/canslim.db"]
TREES = {"data/prices": "*.parquet", "data/history": "*.csv"}
BRIEF_FILES = ("brief.md", "facts.md", "sources.md")
REQS = "streamlit==1.64.0\npandas>=2.2\npyarrow>=15\nnumpy\nrequests\nbeautifulsoup4\n"

def main():
    for sub in ("tracker_app.py", "canslim", "data"):          # rebuild, keep the bundle's .git
        p = OUT / sub
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    for f in FILES:
        (OUT / f).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / f, OUT / f)
    (OUT / "canslim" / "__init__.py").touch()
    for d, pat in TREES.items():
        (OUT / d).mkdir(parents=True, exist_ok=True)
        for f in (ROOT / d).glob(pat):
            shutil.copy2(f, OUT / d / f.name)
    for f in (ROOT / "data/research/companies").glob("*/*.md"):
        if f.name in BRIEF_FILES:
            t = OUT / "data/research/companies" / f.parent.name / f.name
            t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, t)
    (OUT / "requirements.txt").write_text(REQS)
    (OUT / ".streamlit").mkdir(exist_ok=True)
    (OUT / ".streamlit" / "config.toml").write_text("[browser]\ngatherUsageStats = false\n")
    n = sum(1 for p in OUT.rglob("*") if p.is_file() and ".git" not in p.parts)
    mb = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file() and ".git" not in p.parts) / 1e6
    print(f"bundle: {OUT}  {n} files, {mb:.0f} MB")

if __name__ == "__main__":
    main()
