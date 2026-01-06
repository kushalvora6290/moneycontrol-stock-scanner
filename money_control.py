import requests
from collections import defaultdict
from datetime import datetime
import pytz
import os

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8133348298:AAGJuwWrqnF_Qu4CSdSpoovnlGU9J0F2aJw"
CHAT_ID = "-5220624919"

IST = pytz.timezone("Asia/Kolkata")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

COMMON_PARAMS = {
    "deviceType": "W",
    "appVersion": "180",
    "ex": "N",
    "section": "overview",
    "indexId": "7",
    "dur": "1d",
    "page": "1",
    "responseType": "json"
}

APIS = {
    "Top Gainers": ("https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer", 3),
    "Price Shockers": ("https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker", 3),
    "Volume Shockers": ("https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker", 2),
    "Only Buyers": ("https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer", 2),
    "52 Week High": ("https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high", 1),
}

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# =========================
# MARKET TIME CHECK
# =========================
def market_time_ok():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or now.hour > 15:
        return False
    if now.hour == 9 and now.minute < 15:
        return False
    if now.hour == 15 and now.minute > 30:
        return False
    return True

# =========================
# FETCH STOCKS
# =========================
def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        data = r.json()
        return {
            item.get("symbol")
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except:
        return set()

# =========================
# MAIN
# =========================
def main():
    if not market_time_ok():
        return

    scores = defaultdict(int)
    categories = defaultdict(list)

    for name, (url, weight) in APIS.items():
        stocks = fetch_stocks(url)
        for s in stocks:
            scores[s] += weight
            categories[s].append(name)

    if not scores:
        send_telegram(
            "📊 Moneycontrol Intraday Scanner\n\n"
            "⚠ No data received from Moneycontrol APIs."
        )
        return

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"

    for stock, score in ranked[:10]:
        cats = ", ".join(categories[stock])
        msg += f"• {stock} | Score {score} | {cats}\n"

    send_telegram(msg)

if __name__ == "__main__":
    main()
