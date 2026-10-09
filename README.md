# Asura Scans Chapter Alerts

Checks your manhwa list every 4 hours on GitHub Actions and sends a Telegram alert on new chapters.

## Setup (one time, ~10 min)

### 1. Telegram bot
1. In Telegram, open **@BotFather** -> send `/newbot` -> follow prompts. Copy the **token**.
2. Open your new bot and send it any message (e.g. "hi").
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser.
   Find `"chat":{"id":123456789` -> that number is your **chat ID**.

### 2. GitHub repo
1. Create a new repo (public = unlimited free Actions minutes).
2. Upload all files from this folder, including `.github/workflows/check.yml`.
3. Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
   - `TELEGRAM_BOT_TOKEN` = your token
   - `TELEGRAM_CHAT_ID` = your chat ID
4. Repo -> Settings -> Actions -> General -> Workflow permissions -> **Read and write permissions** -> Save.

### 3. Add your manhwas
Edit `series.json`. For each series, open it on Asura Scans and copy the **series page URL**
(the one that lists all chapters, NOT a single chapter):

```json
[
  { "name": "Solo Leveling", "url": "https://asuracomic.net/series/solo-leveling-xxxx" },
  { "name": "Another One",   "url": "https://asuracomic.net/series/another-one-yyyy" }
]
```

### 4. Test it
Actions tab -> "Check new chapters" -> **Run workflow**.
Open the run log: you should see `[INIT] ... tracking from chapter N` for each series.
(First run only saves current chapters, so no alerts. Alerts begin with the next new chapter.)

To test the alert itself, edit `state.json` and lower one value (e.g. "150" -> "149"), then run again.

## Daily use
Nothing. To add/remove a series, edit `series.json`.

## Troubleshooting
- **Domain changed** (asuracomic.net -> something else): update the URLs in `series.json`.
- **"No chapter links found"**: wrong URL, or the site changed. Re-copy the series URL from your browser.
- **403 / Cloudflare errors**: GitHub's IPs may be blocked. Run it on your own PC/Raspberry Pi
  with cron instead (see below), or tell me and I'll add a Playwright version.
- **No Telegram message**: check secrets are named exactly as above and you messaged the bot first.
- **Workflow stopped**: GitHub pauses schedules after 60 days of repo inactivity. Re-enable in Actions tab.

## Run locally (optional)
```
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy   # Windows: set VAR=value
python tracker.py
```
