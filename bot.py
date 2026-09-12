"""
Loot Scout resale-opportunity bot.

Searches Vinted and Wallapop for:
  1) specific watchlisted titles (flags if price looks like a steal)
  2) a broad sweep of retro-gaming / Funko keywords (flags any new match)

Sends alerts to a Telegram chat. Designed to run on a schedule via
GitHub Actions (see .github/workflows/scan.yml) -- state (which listings
have already been alerted on) is kept in seen_items.json, which the
workflow commits back to the repo after every run so duplicates aren't
re-sent.

Env vars required:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import json
import os
import time
import requests

WATCHLIST_PATH = "watchlist.json"
SEEN_PATH = "seen_items.json"

VINTED_SEARCH_URL = "https://www.vinted.es/api/v2/catalog/items"
WALLAPOP_SEARCH_URL = "https://api.wallapop.com/api/v3/general/search"

HEADERS_VINTED = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/119.0 Mobile Safari/537.36",
    "Accept": "application/json",
}
HEADERS_WALLAPOP = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/119.0 Mobile Safari/537.36",
    "Accept": "application/json",
    "X-DeviceOS": "0",
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=15)
    if not resp.ok:
        print("Telegram send failed:", resp.status_code, resp.text)


_vinted_session = None


def get_vinted_session():
    """Vinted's API rejects cold requests with 401. Visiting the site
    first, like a real browser would, gets us a valid session cookie
    we can reuse for the actual search calls."""
    global _vinted_session
    if _vinted_session is not None:
        return _vinted_session
    s = requests.Session()
    s.headers.update(HEADERS_VINTED)
    try:
        s.get("https://www.vinted.es/", timeout=15)
    except Exception as e:
        print("Vinted warm-up request failed:", e)
    _vinted_session = s
    return s


def search_vinted(query, min_price=None, max_price=None):
    params = {
        "search_text": query,
        "order": "newest_first",
        "per_page": 20,
    }
    if min_price:
        params["price_from"] = min_price
    if max_price:
        params["price_to"] = max_price
    try:
        session = get_vinted_session()
        resp = session.get(VINTED_SEARCH_URL, params=params, timeout=15)
        if resp.status_code == 401:
            # Session cookie may have expired mid-run -- refresh once and retry.
            global _vinted_session
            _vinted_session = None
            session = get_vinted_session()
            resp = session.get(VINTED_SEARCH_URL, params=params, timeout=15)
        if not resp.ok:
            print(f"Vinted search failed for '{query}':", resp.status_code)
            return []
        data = resp.json()
        items = []
        for it in data.get("items", []):
            items.append({
                "source": "Vinted",
                "id": f"vinted-{it.get('id')}",
                "title": it.get("title"),
                "price": float(it.get("price", {}).get("amount", 0)),
                "currency": it.get("price", {}).get("currency_code", "EUR"),
                "url": it.get("url"),
            })
        return items
    except Exception as e:
        print(f"Vinted error for '{query}':", e)
        return []


_wallapop_session = None


def get_wallapop_session():
    global _wallapop_session
    if _wallapop_session is not None:
        return _wallapop_session
    s = requests.Session()
    s.headers.update(HEADERS_WALLAPOP)
    try:
        s.get("https://es.wallapop.com/", timeout=15)
    except Exception as e:
        print("Wallapop warm-up request failed:", e)
    _wallapop_session = s
    return s


def search_wallapop(query, min_price=None, max_price=None):
    params = {
        "keywords": query,
        "latitude": "41.3874",   # Barcelona -- adjust if needed
        "longitude": "2.1686",
        "distance": "300000",    # 300km radius, in meters
        "order_by": "newest",
    }
    if min_price:
        params["min_sale_price"] = min_price
    if max_price:
        params["max_sale_price"] = max_price
    try:
        session = get_wallapop_session()
        resp = session.get(WALLAPOP_SEARCH_URL, params=params, timeout=15)
        if not resp.ok:
            print(f"Wallapop search failed for '{query}':", resp.status_code)
            return []
        data = resp.json()
        items = []
        for it in data.get("search_objects", []):
            items.append({
                "source": "Wallapop",
                "id": f"wallapop-{it.get('id')}",
                "title": it.get("title") or it.get("content", {}).get("title", ""),
                "price": float(it.get("price", 0)),
                "currency": it.get("currency", "EUR"),
                "url": f"https://es.wallapop.com/item/{it.get('web_slug', it.get('id'))}",
            })
        return items
    except Exception as e:
        print(f"Wallapop error for '{query}':", e)
        return []


def check_watchlist(config, seen, token, chat_id):
    for entry in config["watchlist"]:
        title = entry["title"]
        est_value = entry.get("estimated_value_eur")
        threshold = est_value * config.get("alert_below_ratio", 0.55) if est_value else None

        results = search_vinted(title) + search_wallapop(title)
        for item in results:
            if item["id"] in seen:
                continue
            seen[item["id"]] = int(time.time())

            price = item["price"]
            if price <= 0:
                continue
            if config.get("min_price_eur") and price < config["min_price_eur"]:
                continue

            is_deal = threshold is not None and price <= threshold
            flag = "🔥 POTENTIAL STEAL" if is_deal else "👀 New listing"

            text = (
                f"{flag}\n"
                f"<b>{item['title']}</b>\n"
                f"Watchlist match: {title} ({entry.get('console', '?')})\n"
                f"Price: {price:.2f} {item['currency']}"
                + (f" (est. value ~{est_value}€)" if est_value else "")
                + f"\nSource: {item['source']}\n"
                + f"{item['url']}"
            )
            send_telegram(token, chat_id, text)
            time.sleep(1)


def check_broad_sweep(config, seen, token, chat_id):
    for kw in config.get("broad_sweep_keywords", []):
        results = search_vinted(kw, config.get("min_price_eur"), config.get("max_price_eur")) \
            + search_wallapop(kw, config.get("min_price_eur"), config.get("max_price_eur"))
        for item in results:
            if item["id"] in seen:
                continue
            seen[item["id"]] = int(time.time())

            price = item["price"]
            if price <= 0:
                continue

            text = (
                f"📦 Broad sweep match: \"{kw}\"\n"
                f"<b>{item['title']}</b>\n"
                f"Price: {price:.2f} {item['currency']}\n"
                f"Source: {item['source']}\n"
                f"{item['url']}"
            )
            send_telegram(token, chat_id, text)
            time.sleep(1)


def prune_seen(seen, max_age_days=30):
    cutoff = int(time.time()) - max_age_days * 86400
    return {k: v for k, v in seen.items() if v >= cutoff}


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars")

    config = load_json(WATCHLIST_PATH, {})
    seen = load_json(SEEN_PATH, {})

    check_watchlist(config, seen, token, chat_id)
    check_broad_sweep(config, seen, token, chat_id)

    seen = prune_seen(seen)
    save_json(SEEN_PATH, seen)


if __name__ == "__main__":
    main()
