"""
Asura Scans new-chapter alerts via Telegram.

Reads series.json, checks each series page for its newest chapter,
compares with state.json, and sends a Telegram message for new chapters.
Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json
import math
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


def clean_series_url(url: str) -> str:
    """Strip any trailing '/chapter/N' so the URL is the series page."""
    url = url.strip().rstrip("/")
    while re.search(r"/chapter[/-]\d+(?:\.\d+)?$", url):
        url = re.sub(r"/chapter[/-]\d+(?:\.\d+)?$", "", url)
    return url


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


def get_latest_generic(series_url: str) -> float:
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


def fetch(url: str):
    return http.get(url, headers=HEADERS, timeout=30, **EXTRA)


# ---------------------------------------------------------------- Mgeko ----
def get_latest_mgeko(url: str):
    """Series page: https://www.mgeko.cc/manga/<slug>/  (reader URLs also accepted)."""
    path = urlparse(url).path
    m = re.search(r"/reader/en/(.+?)-chapter-\d", path)
    if m:
        slug = m.group(1)
    else:
        m = re.search(r"/manga/([^/]+)", path)
        if not m:
            raise RuntimeError("Mgeko URL should look like https://www.mgeko.cc/manga/<name>/")
        slug = m.group(1)
    series_page = f"https://www.mgeko.cc/manga/{slug}/"

    resp = fetch(series_page)
    text = resp.text

    def scan(slug_part: str):
        pat = (r"""(/reader/en/""" + slug_part +
               r"""-chapter-(\d+(?:-\d+)?)[^"'\s<>)]*)""")
        return [(float(n.replace("-", ".")), p) for p, n in re.findall(pat, text)]

    found = scan(re.escape(slug)) or scan(r"[a-z0-9-]+?")
    if not found:
        raise RuntimeError(f"No chapters found (HTTP {resp.status_code}, title={_title(text)!r}).")
    num, link_path = max(found, key=lambda x: x[0])
    return num, "https://www.mgeko.cc" + link_path


# ------------------------------------------------------- Demonic Scans -----
def get_latest_demonic(url: str):
    """Series page: https://demonicscans.org/manga/<Name>  (chaptered.php URLs also accepted)."""
    series_page = url
    if "/manga/" not in urlparse(url).path:
        # e.g. chaptered.php?manga=14033&chapter=35 -> redirects to /title/<Name>/chapter/35/1
        r = fetch(url)
        m = (re.search(r"/title/([^/]+)/", str(r.url))
             or re.search(r"""href=["'](?:https://demonicscans\.org)?/manga/([^"'/]+)["']""", r.text))
        if not m:
            raise RuntimeError("Could not find the series page. Use https://demonicscans.org/manga/<Name>")
        series_page = f"https://demonicscans.org/manga/{m.group(1)}"

    resp = fetch(series_page)
    found = re.findall(r"chaptered\.php\?manga=(\d+)(?:&amp;|&)chapter=(\d+(?:\.\d+)?)", resp.text)
    if not found:
        raise RuntimeError(f"No chapters found (HTTP {resp.status_code}, title={_title(resp.text)!r}).")
    manga_id, num = max(found, key=lambda x: float(x[1]))
    return float(num), f"https://demonicscans.org/chaptered.php?manga={manga_id}&chapter={num}"


# -------------------------------------------------------- Vortex Scans ----
def get_latest_vortex(url: str, known=None):
    """
    Series page: https://vortexscans.org/series/<slug>
    The public chapter list on that page can lag behind the newest chapters,
    so after reading it we also probe the next chapter URLs directly.
    `known` = highest chapter already known (from state.json or a pasted chapter link).
    """
    m = re.match(r"/series/([^/]+)", urlparse(url).path)
    if not m:
        raise RuntimeError("Vortex URL should look like https://vortexscans.org/series/<name>")
    slug = m.group(1)
    base = f"https://vortexscans.org/series/{slug}"

    resp = fetch(base)
    pat = re.escape(f"/series/{slug}/chapter-") + r"(\d+(?:\.\d+)?)"
    listed = [float(n) for n in re.findall(pat, resp.text)]
    start = max(listed + ([known] if known else []), default=None)
    if start is None:
        raise RuntimeError(f"No chapters found (HTTP {resp.status_code}, title={_title(resp.text)!r}).")

    latest, n, misses = start, math.floor(start) + 1, 0
    for _ in range(8):  # max probes per run
        time.sleep(1)
        if _vortex_chapter_exists(base, n):
            latest, misses = float(n), 0
        else:
            misses += 1
            if misses >= 2:  # allow one skipped number
                break
        n += 1
    return latest, f"{base}/chapter-{fmt(latest)}"


def _vortex_chapter_exists(base: str, n) -> bool:
    num = fmt(n)
    r = fetch(f"{base}/chapter-{num}")
    if r.status_code != 200 or not str(r.url).rstrip("/").endswith(f"/chapter-{num}"):
        return False
    n_re = re.escape(num)
    return bool(
        re.search(rf"Chapter\s*{n_re}\s*Page\s*1\b", r.text)
        or re.search(rf"<title>[^<]*Chapter\s*{n_re}\b[^<]*</title>", r.text)
    )


def _title(text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    return m.group(1).strip()[:80] if m else ""


# ---------------------------------------------------------- dispatcher -----
def get_latest(series_url: str, known=None):
    """Return (latest_chapter_number, link_to_it) using the right site logic."""
    host = urlparse(series_url).netloc.lower()
    if "vortexscans" in host:
        return get_latest_vortex(series_url, known)
    if "mgeko" in host:
        return get_latest_mgeko(series_url)
    if "demonicscans" in host:
        return get_latest_demonic(series_url)
    # Asura Scans and any similar site that uses .../chapter/N links
    n = get_latest_generic(series_url)
    return n, f"{series_url}/chapter/{fmt(n)}"


def send_telegram(text: str) -> None:
    """Send to every chat ID in TELEGRAM_CHAT_ID (comma-separated)."""
    chat_ids = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
    if not BOT_TOKEN or not chat_ids:
        print(f"[no Telegram creds] {text}")
        return
    for chat_id in chat_ids:
        try:
            r = http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": text},
                timeout=30,
            )
            if r.status_code != 200:
                print(f"Telegram error for {chat_id}: {r.status_code} {r.text}")
        except Exception as ex:
            print(f"Telegram error for {chat_id}: {ex}")


def main() -> int:
    series_list = json.loads(SERIES_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    failures = 0

    for s in series_list:
        name = s["name"]
        raw_url = s["url"].strip().rstrip("/")
        url = clean_series_url(raw_url)
        # migrate state saved under an old, un-cleaned URL
        if url not in state and raw_url in state:
            state[url] = state.pop(raw_url)
        last_seen = state.get(url)
        # highest chapter we already know of (state, or a chapter link you pasted)
        hints = [x for x in (chapter_from_url(raw_url),
                             float(last_seen) if last_seen is not None else None)
                 if x is not None]
        try:
            latest, link = get_latest(url, max(hints, default=None))
        except Exception as e:
            failures += 1
            print(f"[FAIL] {name}: {e}")
            continue

        if last_seen is None:
            # First time: save silently so you don't get spammed.
            state[url] = fmt(latest)
            print(f"[INIT] {name}: tracking from chapter {fmt(latest)}")
        elif latest > float(last_seen):
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
