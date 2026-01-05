import os
import time
import requests
import pandas as pd
import yfinance as yf
from collections import defaultdict

# =========================
# CONFIG (GitHub Secrets)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# MONEYCONTROL CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.moneycontrol.com/",
    "Origin": "https://www.moneycontrol.com"
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
    "Volume Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker",
    "Only Buyers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer",
    "Price Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker",
    "Top Gainers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer",
    "52 Week High": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high"
}

# =========================
# CATEGORY WEIGHTS (KEY FIX)
# =========================
CATEGORY_WEIGHT = {
    "Volume Shockers": 3,
    "Only Buyers": 3,
    "Price Shockers": 2,
    "Top Gainers": 1,
    "52 Week High": 1
}

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠ Telegram credentials missing")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# =========================
# FETCH MONEYCONTROL DATA
# =========================
def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        if r.status_code != 200:
            return set()

        data = r.json()
        return {
            item.get("symbol")
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except Exception:
        return set()

# =========================
# TECHNICAL INDICATORS
# =========================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# INTRADAY TRANSITION LOGIC
# =========================
alerted_stocks = set()

def intraday_transition_alert(stock, score):
    try:
        df = yf.download(
            stock + ".NS",
            interval="5m",
            period="1d",
            progress=False
        )

        if df.empty or len(df) < 20:
            return

        df["RSI"] = compute_rsi(df["Close"])

        df["VWAP"] = (
            df["Volume"]
            * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()

        price = df["Close"].iloc[-1]
        vwap = df["VWAP"].iloc[-1]
        rsi_now = df["RSI"].iloc[-1]
        rsi_prev = df["RSI"].iloc[-2]

        # FIX: Correct market open (09:15–09:45 IST)
        first_30m = df.between_time("09:15", "09:45")
        if first_30m.empty:
            return

        first_high = first_30m["High"].max()

        # REAL INTRADAY CONFIRMATION
        if (
            stock not in alerted_stocks
            and price > vwap
            and price > first_high
            and rsi_now > rsi_prev
            and 55 <= rsi_now <= 75
        ):
            alerted_stocks.add(stock)

            send_telegram(
                f"🚨 INTRADAY BREAKOUT ALERT\n\n"
                f"STOCK: {stock}\n"
                f"Strength Score: {score}\n"
                f"RSI(14): {round(rsi_now, 2)}\n"
                f"VWAP: Reclaimed\n"
                f"Breakout: First 30-min High\n\n"
                f"✅ ACTIONABLE INTRADAY"
            )

    except Exception:
        pass

# =========================
# MAIN
# =========================
def main():
    stock_categories = defaultdict(list)

    # ---- FETCH ALL CATEGORIES
    for category, url in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(1)
        for s in stocks:
            stock_categories[s].append(category)

    # ---- WEIGHTED RAW MOMENTUM
    raw_list = []

    for stock, cats in stock_categories.items():
        score = sum(CATEGORY_WEIGHT.get(c, 0) for c in cats)

        if score >= 5 and (
            "Volume Shockers" in cats or "Only Buyers" in cats
        ):
            raw_list.append((stock, score, cats))

    # ---- SEND RAW SNAPSHOT
    if raw_list:
        msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
        for stock, score, cats in sorted(raw_list, key=lambda x: x[1], reverse=True)[:15]:
            msg += f"• {stock} | Score {score} | {', '.join(cats)}\n"

        send_telegram(msg)

    # ---- CHECK LIVE INTRADAY TRANSITIONS
    for stock, score, _ in raw_list:
        intraday_transition_alert(stock, score)

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    main()
