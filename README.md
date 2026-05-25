# open-calls

Weekly digest of open calls, residencies, fellowships, and opportunities in art and creative technology.

Runs every Monday at 8am UTC via GitHub Actions. Results committed to `digest/YYYY-MM-DD.md`.

## sources

**RSS**
- Rhizome
- Creative Applications
- SFPC (School for Poetic Computation)
- Residency Unlimited
- ResArtis
- Canada Council for the Arts
- Ars Electronica

**Scraped**
- Eyebeam
- InterAccess (Toronto)
- Harbourfront Centre (Toronto)
- Gray Area (SF)
- Onassis ONX (NYC)
- transmediale (Berlin)
- MUTEK (Montreal)
- Ontario Arts Council
- Creative Capital
- La Gaîté Lyrique (Paris)
- Blank100
- CAFE (callforentry.org)

## setup

### 1. Clone and push to your GitHub

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/open-calls.git
git push -u origin main
```

### 2. Set up Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you
4. Message your bot once to start a chat
5. Get your chat ID: visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`

### 3. Add GitHub secrets

In your repo: Settings → Secrets and variables → Actions → New repository secret

- `TELEGRAM_BOT_TOKEN` — the token from BotFather
- `TELEGRAM_CHAT_ID` — your chat ID from getUpdates

### 4. Enable GitHub Pages (optional)

To browse digests as a simple site, enable Pages from the `main` branch.

### 5. Run manually

Go to Actions → Weekly Open Calls Digest → Run workflow

## local run

```bash
pip install -r requirements.txt
playwright install chromium
python scrape.py
```

## adding sources

**RSS source:** add an entry to `RSS_FEEDS` in `scrape.py`
**Scraped source:** add an entry to `SCRAPE_TARGETS` in `scrape.py`
