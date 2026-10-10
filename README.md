# Manhwa Chapter Alerts (Asura Scans → Telegram)

Get a **Telegram message on your phone** whenever a manhwa you follow on [Asura Scans](https://asurascans.com) releases a new chapter.

It runs for free on **GitHub Actions**. No server, no app, and nothing to keep running on your PC.

```
GitHub Actions (every hour)
        │
        ▼
 tracker.py  ──►  checks each series on Asura Scans
        │
        ├─ compares with state.json (last chapter seen)
        │
        └─ new chapter? ──►  Telegram message to your phone
```

---

## Features

- Track **as many series as you want**
- Free: runs on GitHub Actions (unlimited minutes on public repos)
- Phone notification with chapter number and direct link
- No duplicate alerts: remembers the last chapter per series
- First run saves current chapters silently, so you aren't flooded
- One failing series doesn't stop the others
- Prints debug info if a site check fails

---

## Repository structure

| File | Purpose |
|---|---|
| `tracker.py` | Main script: fetches chapters, compares, sends alerts |
| `series.json` | **Your list of manhwas** (you edit this) |
| `state.json` | Last chapter seen per series (updated automatically by the bot) |
| `requirements.txt` | Python dependencies |
| `.github/workflows/check.yml` | The scheduler that runs the script |

---

## Setup (one time, about 10 minutes)

### 1. Fork or copy this repo

Click **Fork** (top right), or create a new repo and upload all files.
If you upload manually, make sure the `.github/workflows/check.yml` path is kept exactly.

> **Use a public repo** for unlimited free Actions minutes.

### 2. Create a Telegram bot

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and follow the prompts. Copy the **bot token**. It looks like `123456789:ABC-DEF...`.
3. Open your new bot, press **Start**, and send it any message (e.g. `hi`). The bot won't reply. That's normal.

### 3. Get your chat ID

Open this link in a browser, replacing `YOUR_TOKEN` with your bot token (no spaces, no `< >`):

```
https://api.telegram.org/botYOUR_TOKEN/getUpdates
```

Find `"chat":{"id":` and copy the number after it. That's your **chat ID**, digits only (e.g. `987654321`).

If the result is empty (`"result":[]`), message your bot again and refresh.

### 4. Add GitHub secrets

In your repo go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | your bot token |
| `TELEGRAM_CHAT_ID` | your chat ID (digits only) |

Names must match exactly.

### 5. Allow the bot to save its state

Go to **Settings → Actions → General → Workflow permissions**, select **Read and write permissions**, and click **Save**.

### 6. Add your manhwas

Edit `series.json`:

```json
[
  {
    "name": "Reincarnation of the Fist King",
    "url": "https://asurascans.com/comics/reincarnation-of-the-fist-king-bd5bdaf8"
  },
  {
    "name": "Another Series",
    "url": "https://asurascans.com/comics/another-series-xxxxxxxx"
  }
]
```

**How to get the URL:**
1. Open the series on asurascans.com.
2. Copy the address ending in `/comics/<name>-<code>`.
3. If the address ends with `/chapter/NN`, delete that part.

`name` is just the label shown in your alert. Call it anything.

### 7. Reset the state and run a test

1. Make sure `state.json` contains just `{}`.
2. Go to the **Actions** tab. If asked, click **enable workflows**.
3. Choose **Check new chapters → Run workflow → Run workflow**.
4. Open the run and read the **Run tracker** log. You should see:
   ```
   [INIT] Your Series: tracking from chapter 102
   ```
   The first run sends no Telegram message. It only records the current chapters.

### 8. Test the alert

1. Edit `state.json` and lower one number by 1 (e.g. `"102"` → `"101"`), then commit.
2. Run the workflow again.
3. Your bot should message you with the chapter and link.

Done. From now on it runs automatically.

---

## Daily use

You don't need to do anything. You get a Telegram message when a new chapter appears.

- **Add a series:** add an entry to `series.json`.
- **Remove a series:** delete its entry from `series.json`.
- **Change how often it checks:** edit the `cron` line in `.github/workflows/check.yml`:

| Cron | Runs |
|---|---|
| `17 * * * *` | every hour at minute 17 (default) |
| `0 */4 * * *` | every 4 hours |
| `0 */12 * * *` | every 12 hours |

Times are in UTC. GitHub may delay scheduled runs by 5–15 minutes. Checking more often than hourly isn't recommended.

---

## How it works

1. GitHub starts a temporary machine on the schedule.
2. `tracker.py` loads `series.json` and `state.json`.
3. For each series it opens the series URL. Asura redirects this to a chapter page, so the script reads the chapter number from the final URL, scans for chapter links belonging to that series, and follows "next chapter" links until it reaches the newest one.
4. If the newest chapter is higher than the one in `state.json`, it sends a Telegram message and saves the new number.
5. The workflow commits the updated `state.json` back to the repo, and the machine shuts down.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "There are no workflow runs yet" | Scheduled runs only start at the next interval. Start one manually with **Run workflow**. If the workflow isn't listed, check the file is at `.github/workflows/check.yml`. |
| `No chapter found` | Re-copy the series URL. Check the `[debug]` lines in the log for the status code, final URL and page title. |
| Page title says "Just a moment..." or HTTP 403 | Cloudflare is blocking GitHub's servers. Run the script on your own PC or a Raspberry Pi instead (see below). |
| No Telegram message | Check the secret names, that the chat ID is digits only, and that you pressed **Start** in your bot's chat. Look for `Telegram error` in the log. |
| `state.json` not saving / push error | Enable **Read and write permissions** (setup step 5). |
| Domain changed | Update the URLs in `series.json`. |
| Scheduled runs stopped | GitHub pauses schedules after about 60 days with no repo activity. Re-enable in the Actions tab. |

---

## Run it locally (optional)

```bash
pip install -r requirements.txt

# Linux / macOS
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Windows (PowerShell)
# $env:TELEGRAM_BOT_TOKEN="your_token"
# $env:TELEGRAM_CHAT_ID="your_chat_id"

python tracker.py
```

To check on a schedule, use `cron` on Linux/macOS or Task Scheduler on Windows.

---

## Notes and limitations

- Asura Scans has no official API. This tool reads the public website, so a site redesign, domain change or stronger bot protection can break it. The `[debug]` output in the log helps diagnose this.
- Please keep the check interval reasonable (1–4 hours) to avoid putting load on the site, and respect the site's terms of use.
- This is an unofficial personal tool and is not affiliated with Asura Scans.
- Never commit your bot token. Keep it in GitHub **Secrets** only.
