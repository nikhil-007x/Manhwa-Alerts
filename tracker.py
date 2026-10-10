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
from urllib.parse import urljoin, urlparse

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

MAX_HOPS = 15  # max "next chapter" pages to follow per series

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def fmt(num: float) -> str:
    """101.0 -> '101', 101.5 -> '101.5'"""
    return str(int(num)) if float(num).is_integer() else str(num)


def chapter_from_url(u: str):
    """'.../chapter/72' -> 72.0, else None."""
    m = re.search(r"/chapter[/-](\d+(?:\.\d+)?)/?(?:[?#].*)?$", u)
    return float(m.group(1)) if m else None


def find_next_link(text: str):
    """Return href of <link rel="next"> / <a rel="next"> if present."""
    for tag in re.findall(r"<(?:link|a)\b[^>]*>", text):
        if re.search(r"""rel=["']?next""", tag):
            m = re.search(r"""href=["']([^"']+)["']""", tag)
            if m:
                return m.group(1)
    return None


def get_latest_chapter(series_url: str) -> float:
    """
    Asura redirects a series URL to a chapter page, so we:
      1. read the chapter number from the final URL,
      2. read any chapter links for this series on the page,
      3. follow rel="next" links (if any) until the newest chapter.
    """
    slug = urlparse(series_url).path.rstrip("/").split("/")[-1].lower()
    core = re.sub(r"-[0-9a-f]{6,10}$", "", slug)

    resp = http.get(series_url, headers=HEADERS, timeout=30, **EXTRA)
    candidates, seen = [], set()

    for _ in range(MAX_HOPS):
        final = str(resp.url)
        n = chapter_from_url(final)
        if n is not None:
            candidates.append(n)

        text = resp.text.replace("\\/", "/")
        for m in re.finditer(r"""([^\s"'<>()]*?)/chapter[/-](\d+(?:\.\d+)?)""", text):
            if core in m.group(1).lower():
                candidates.append(float(m.group(2)))

        nxt = find_next_link(text)
        if not nxt:
            break
        nxt_url = urljoin(final, nxt)
        if nxt_url in seen or chapter_from_url(nxt_url) is None:
            break
        seen.add(nxt_url)
        time.sleep(1)
        resp = http.get(nxt_url, headers=HEADERS, timeout=30, **EXTRA)

    if candidates:
        return max(candidates)

    title = re.search(r"<title>(.*?)</title>", resp.text, re.S | re.I)
    print(f"  [debug] status={resp.status_code} final_url={resp.url}")
    print(f"  [debug] title={title.group(1).strip()[:100] if title else None} length={len(resp.text)}")
    raise RuntimeError(f"No chapter found (HTTP {resp.status_code}).")


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
