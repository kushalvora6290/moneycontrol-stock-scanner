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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
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
    "Top Gainers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer",
    "Only Buyers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer",
    "Price Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker",
    "Volume Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker",
    "52 Week High": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high",
}

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠ Telegram secrets missing")
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
# MONEYCONTROL FETCH
# =========================
def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        if r.status_code != 200 or not r.text.strip():
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
# TECHNICALS
# =========================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Prevent duplicate alerts (per run)
alerted_stocks = set()

def intraday_transition_alert(stock, category_count):
    try:
        df = yf.download(stock + ".NS", interval="5m", period="1d", progress=False)
        if df.empty or len(df) < 20:
            return

        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = (
            df["Volume"]
            * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()

        price = df.iloc[-1]["Close"]
        vwap = df.iloc[-1]["VWAP"]

        rsi_now = df["RSI"].iloc[-1]
        rsi_prev = df["RSI"].iloc[-2]

        first_30m = df.between_time("09:15", "09:45")
        if first_30m.empty:
            return

        first_high = first_30m["High"].max()

        # RAW → CONFIRMED TRANSITION
        if (
            stock not in alerted_stocks
            and price > vwap
            and rsi_now > rsi_prev
            and 55 <= rsi_now <= 75
            and price > first_high
        ):
            alerted_stocks.add(stock)

            send_telegram(
                f"🚨 INTRADAY BREAKOUT ALERT\n\n"
                f"STOCK: {stock}\n"
                f"Categories: {category_count}\n"
                f"RSI: {round(rsi_now, 2)}\n"
                f"VWAP: Reclaimed\n"
                f"Breakout: First 30-min High\n\n"
                f"✅ ACTIONABLE NOW"
            )

    except Exception:
        pass

# =========================
# MAIN
# =========================
def main():
    stock_categories = defaultdict(list)

    # ---- Build RAW MOMENTUM
    for category, url in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(1.2)
        for s in stocks:
            stock_categories[s].append(category)

    raw_list = [
        (stock, len(cats))
        for stock, cats in stock_categories.items()
        if len(cats) >= 2
    ]

    # ---- Send RAW snapshot once
    if raw_list:
        msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
        for s, c in sorted(raw_list, key=lambda x: x[1], reverse=True)[:15]:
            msg += f"• {s} ({c})\n"
        send_telegram(msg)

    # ---- Check LIVE TRANSITIONS
    for stock, count in raw_list:
        intraday_transition_alert(stock, count)

if __name__ == "__main__":
    main()
