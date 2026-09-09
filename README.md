# Loot Scout Marketplace Bot

Scans Vinted and Wallapop every 20 minutes for retro-gaming resale
opportunities and sends alerts to Telegram — runs for free on GitHub
Actions, no server or always-on device needed.

## What it does

1. **Watchlist mode** — checks specific high-value titles
   (`watchlist.json`) across PS1/PS2/PS3, N64, GameCube, Genesis,
   Dreamcast, NES and more. If a listing's price is well below the
   estimated resale value, it's flagged 🔥 as a potential steal.
2. **Broad sweep mode** — searches generic terms like "lote juegos
   ps2", "funko pop lote", "retro games bundle" and alerts on any new
   listing so you don't miss bundles/lots that wouldn't match a
   specific title search.

Every listing is only alerted once (tracked in `seen_items.json`,
which the workflow commits back to the repo after each run).

## Setup (10 minutes)

1. **Create a GitHub repo** and upload all these files
   (`bot.py`, `watchlist.json`, `requirements.txt`, `seen_items.json`,
   `.github/workflows/scan.yml`, this README).

2. **Add your Telegram credentials as repo secrets:**
   - Go to your repo → Settings → Secrets and variables → Actions →
     "New repository secret"
   - Add `TELEGRAM_BOT_TOKEN` = your bot's token
   - Add `TELEGRAM_CHAT_ID` = your chat id (104583796)

3. **Enable Actions** on the repo if not already (Settings → Actions
   → General → Allow all actions).

4. **Test it manually:** go to the Actions tab → "Loot Scout
   Marketplace Scan" → "Run workflow" → Run. Check the logs, and
   check Telegram for alerts.

5. Once confirmed working, it runs automatically every 20 minutes.

## Tuning

- **Watchlist** (`watchlist.json` → `watchlist`): add/remove titles,
  adjust `estimated_value_eur` per title as market prices move —
  check PriceCharting.com periodically to keep these current.
- **Deal threshold**: `alert_below_ratio` (default 0.55) — a listing
  is flagged as a steal if its price is under 55% of the estimated
  value. Lower = stricter, fewer alerts.
- **Broad sweep keywords**: add more search terms as needed. Keep in
  mind more keywords = more API calls = higher chance of hitting rate
  limits, so don't go overboard.
- **Price range**: `min_price_eur` / `max_price_eur` cap what the
  broad sweep considers (filters out obvious junk or joke listings).
- **Schedule frequency**: edit the cron line in
  `.github/workflows/scan.yml` (`*/20 * * * *` = every 20 min).
  GitHub free tier gives 2,000 Actions minutes/month for private
  repos (unlimited for public repos) — 20-min interval comfortably
  fits either.

## Important notes

- **Unofficial APIs**: this uses Vinted's and Wallapop's internal
  (undocumented) search endpoints — the same ones their own apps
  call. They can change without notice, which would break the
  script; if alerts suddenly stop, that's the first thing to check.
- **Respect rate limits**: the script already spaces out Telegram
  sends; if you add many more keywords/titles, consider increasing
  the schedule interval so you're not hammering either marketplace's
  servers.
- **Security**: your bot token is a secret — never commit it directly
  into `bot.py` or `watchlist.json`. It only ever lives in GitHub's
  encrypted repo secrets and is injected as an environment variable
  at runtime.
