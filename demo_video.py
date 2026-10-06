"""Record a narrated demo video of the tracker app (read-only: nothing is saved to the database).

Needs the app running at http://localhost:8501 (run_app.bat).
Output: data/demo/canslim_app_demo.mp4

usage: python demo_video.py
"""
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "demo"
URL = "http://localhost:8501"
W, H = 1440, 900

CAPTION_JS = """([title, text]) => {
  let el = document.getElementById('demo-cap');
  if (!el) {
    el = document.createElement('div'); el.id = 'demo-cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:999999;' +
      'max-width:1100px;padding:14px 22px;border-radius:12px;background:rgba(15,23,42,.92);color:#fff;' +
      'font:16px/1.45 Segoe UI,Arial,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.35);transition:opacity .3s';
    document.body.appendChild(el);
  }
  el.style.opacity = text ? '1' : '0';
  el.innerHTML = (title ? '<div style="font-weight:700;font-size:18px;color:#fbbf24;margin-bottom:4px">' + title + '</div>' : '') + (text || '');
}"""

CARD_JS = """([title, lines]) => {
  let el = document.getElementById('demo-card');
  if (!title) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'demo-card'; document.body.appendChild(el); }
  el.style.cssText = 'position:fixed;inset:0;z-index:1000000;display:flex;flex-direction:column;align-items:center;' +
    'justify-content:center;background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fff;font-family:Segoe UI,Arial,sans-serif';
  el.innerHTML = '<div style="font-size:46px;font-weight:800;margin-bottom:18px">' + title + '</div>' +
    lines.map(l => '<div style="font-size:21px;opacity:.9;margin:5px 0">' + l + '</div>').join('');
}"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_raw"
    shutil.rmtree(tmp, ignore_errors=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp),
                            record_video_size={"width": W, "height": H})
        pg = ctx.new_page()

        def wait(s):
            pg.wait_for_timeout(int(s * 1000))

        def cap(title, text=""):
            pg.evaluate(CAPTION_JS, [title, text])

        def card(title, lines=()):
            pg.evaluate(CARD_JS, [title, list(lines)])

        def settle():
            pg.wait_for_timeout(600)
            try:
                pg.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=20000)
            except Exception:
                pass
            pg.wait_for_timeout(800)

        def go(name):
            cap(None, "")
            pg.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
            settle()

        def scroll(total, step=120, pause=0.06):
            pg.mouse.move(W * 0.6, H * 0.5)
            for _ in range(int(abs(total) / step)):
                pg.mouse.wheel(0, step if total > 0 else -step)
                wait(pause)

        def select(label, value):
            box = pg.locator('[data-testid="stSelectbox"]').filter(has_text=label).first
            box.click()
            wait(0.4)
            pg.keyboard.type(value, delay=90)
            wait(0.5)
            pg.keyboard.press("Enter")
            settle()

        pg.goto(URL)
        settle()
        # dismiss Streamlit's promo popup and hide the Deploy toolbar so they don't cover the app
        try:
            pg.get_by_text("Don't show again").click(timeout=4000)
        except Exception:
            pass
        pg.add_style_tag(content='[data-testid="stToolbar"], [data-testid="stHeaderActionElements"] '
                                 '{display: none !important;}')
        card("CAN SLIM Tracker", ["Daily NSE scanner · research only, never places orders",
                                  "Today's picks · Holdings with traffic lights · Research briefs",
                                  "Paper portfolio · Sold-but-watching · Stock lookup · Decision journal"])
        wait(5)
        card(None)

        # ---- Today
        cap("1 · Today", "Every evening the scan runs O'Neil's CAN SLIM rules on ~940 liquid NSE stocks. "
                         "The market filter comes first: in a correction or rally attempt the system makes no new buys.")
        wait(6)
        cap("1 · Today", "Today's list: every stock passing all 8 rules, ranked by relative strength (max 3 per "
                         "industry). 'brief' = the conviction score from the automatic research brief.")
        wait(7)
        scroll(700)
        cap("1 · Today", "Two side lists: Emerging / turnaround names (higher risk) and the Earnings monitor "
                         "(strong fresh results with the price confirming).")
        wait(7)
        scroll(-700)

        # ---- Holdings
        go("Holdings")
        cap("2 · Holdings", "Your real positions get a daily traffic light: GREEN = passes and ranks top 20, "
                            "AMBER = warning signs, RED = the tested sell rule says exit.")
        wait(6)
        pg.get_by_text("How the light works").click()
        wait(1)
        cap("2 · Holdings", "Each buy needs a written plan: why you're buying and what would prove you wrong. "
                            "Holding on a RED light is allowed, but you must write why. That's logged.")
        wait(6)
        scroll(600)
        wait(4)
        scroll(-600)

        # ---- Research
        go("Research")
        select("Company", "TDPOWERSYS")
        cap("3 · Research briefs", "For every new pick, Claude Code reads the concall transcripts and annual "
                                   "report and answers a 12-question conviction checklist, citing sources.")
        wait(6)
        scroll(500)
        cap("3 · Research briefs", "Each answer is scored 0-2 with evidence and the document it came from. "
                                   "Red flags cap the score. The brief suggests; you set the final conviction.")
        wait(7)
        scroll(900)
        wait(3)
        scroll(-1400)
        pg.get_by_role("tab", name="Facts").click()
        settle()
        cap("3 · Research briefs", "Facts tab: the numbers already in the database: quarters, margins, "
                                   "balance sheet, cash flow and shareholding trends.")
        wait(6)
        pg.get_by_role("tab", name="Brief").click()
        settle()

        # ---- Paper portfolio
        go("Paper portfolio")
        cap("4 · Paper portfolio", "The system trades its own lists with Rs 10 lakh of paper money: the live, "
                                   "out-of-sample test. Compared against the Nifty 500.")
        wait(6)
        cap("4 · Paper portfolio", "Right now it's all cash: the market is in a rally attempt, not a confirmed "
                                   "uptrend, so the rules hold off on buying.")
        wait(6)

        # ---- Watching
        go("Watching")
        cap("5 · Sold, still watching", "Every stock that left the list is tracked for 24 months, so a stock that "
                                        "comes back and becomes a big winner isn't missed.")
        wait(6)
        cap("5 · Sold, still watching", "Status: QUALIFIES AGAIN (would be bought back in an uptrend), "
                                        "1 rule away, or not qualifying, with the rules it fails.")
        wait(6)

        # ---- Stock
        go("Stock")
        box = pg.get_by_label("NSE symbol")
        box.fill("")
        box.type("MCX", delay=120)
        box.press("Enter")
        settle()
        cap("6 · Stock lookup", "Any stock: price with 50- and 200-day averages, RS, system rank, profit growth, "
                                "ROE and which rules it fails today.")
        wait(7)
        scroll(600)
        cap("6 · Stock lookup", "Plus its daily history in the system and every day it appeared on a list.")
        wait(5)
        scroll(-600)

        # ---- Journal
        go("Journal")
        cap("7 · Decision journal", "Every buy, hold, sell and note is logged with its reason. It then measures "
                                    "whether overriding the rules (holding on RED) actually helped you.")
        wait(7)
        cap(None, "")
        card("Runs by itself every evening", ["Prices → rules → report → database → paper portfolio → research briefs",
                                              "All local · backed up to a private GitHub repo",
                                              "Research only. Nothing here is an order."])
        wait(5)
        video = pg.video.path()
        ctx.close()
        b.close()

    out = OUT / "canslim_app_demo.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", str(out)],
                   check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"saved {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
