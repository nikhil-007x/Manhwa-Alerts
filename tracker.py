"""
Asura Scans new-chapter alerts via Telegram.

Reads series.json, checks each series page for its newest chapter,
compares with state.json, and sends a Telegram message for new chapters.
Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# curl_cffi mimics a real Chrome browser (helps against Cloudflare).
# Falls back to plain requests if it isn't installed.
try:
    from curl_cffi import requests as http
    EXTRA = {"impersonate": "chrome"}
except ImportError:
    import requests as http
    EXTRA = {}

BASE = Path(__file__).parent
SERIES_FILE = BASE / "series.json"
STATE_FILE = BASE / "state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def fmt(num: float) -> str:
    """101.0 -> '101', 101.5 -> '101.5'"""
    return str(int(num)) if float(num).is_integer() else str(num)


def get_latest_chapter(series_url: str) -> float:
    """Return the highest chapter number linked from the series page."""
    path = urlparse(series_url).path.rstrip("/")
    slug = path.split("/")[-1].lower()
    core = re.sub(r"-[0-9a-f]{6,10}$", "", slug)  # slug without trailing hash

    resp = http.get(series_url, headers=HEADERS, timeout=30, **EXTRA)
    text = resp.text.replace("\\/", "/")  # un-escape JSON-style slashes

    # Find every ".../chapter/N" or ".../chapter-N" and keep only the ones
    # whose URL contains THIS series' slug (ignores sidebars/other series).
    found = []
    for m in re.finditer(r"""([^\s"'<>()]*?)/chapter[/-](\d+(?:\.\d+)?)""", text):
        if core in m.group(1).lower():
            found.append(float(m.group(2)))
    if found:
        return max(found)

    # Nothing found: print diagnostics so we can see why.
    title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    i = text.lower().find("chapter")
    print(f"  [debug] status={resp.status_code} final_url={resp.url}")
    print(f"  [debug] title={title.group(1).strip()[:100] if title else None} length={len(text)}")
    print(f"  [debug] 'chapter' appears {text.lower().count('chapter')} times")
    print(f"  [debug] sample: {text[max(0, i-80):i+160]!r}" if i >= 0 else "  [debug] no 'chapter' text at all")
    raise RuntimeError(f"No chapter links found (HTTP {resp.status_code}).")


def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[no Telegram creds] {text}")
        return
    r = http.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": "false"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Telegram error {r.status_code}: {r.text}")


def main() -> int:
    series_list = json.loads(SERIES_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    failures = 0

    for s in series_list:
        name, url = s["name"], s["url"].rstrip("/")
        try:
            latest = get_latest_chapter(url)
        except Exception as e:
            failures += 1
            print(f"[FAIL] {name}: {e}")
            continue

        last_seen = state.get(url)

        if last_seen is None:
            # First time: save silently so you don't get spammed.
            state[url] = fmt(latest)
            print(f"[INIT] {name}: tracking from chapter {fmt(latest)}")
        elif latest > float(last_seen):
            link = f"{url}/chapter/{fmt(latest)}"
            send_telegram(f"📖 New chapter: {name}\nChapter {fmt(latest)}\n{link}")
            state[url] = fmt(latest)
            print(f"[NEW]  {name}: {last_seen} -> {fmt(latest)}")
        else:
            print(f"[OK]   {name}: still at chapter {fmt(latest)}")

        time.sleep(3)  # be polite between requests

    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
