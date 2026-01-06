import os
import time
import requests
import pandas as pd
import yfinance as yf
from collections import defaultdict
from datetime import datetime, time as dtime
import pytz

# =========================
# TIMEZONE
# =========================
IST = pytz.timezone("Asia/Kolkata")

# =========================
# TELEGRAM (GitHub Secrets)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# HEADERS
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
    "Top Gainers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer",
    "Only Buyers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer",
    "Price Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker",
    "Volume Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker",
    "52 Week High": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high",
}

# =========================
# TELEGRAM SEND
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception:
        pass

# =========================
# MONEYCONTROL FETCH
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
# TECHNICALS
# =========================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# INTRADAY CONFIRMATION
# =========================
alerted_today = set()

def intraday_transition(stock, score):
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

        first_30 = df.between_time("09:15", "09:45")
        if first_30.empty:
            return

        first_high = first_30["High"].max()

        if (
            stock not in alerted_today
            and price > vwap
            and price > first_high
            and rsi_prev < rsi_now
            and 55 <= rsi_now <= 70
        ):
            alerted_today.add(stock)

            send_telegram(
                f"🚨 INTRADAY BREAKOUT\n\n"
                f"STOCK: {stock}\n"
                f"SCORE: {score}\n"
                f"RSI: {round(rsi_now, 2)}\n"
                f"VWAP: Above\n"
                f"Breakout: 30-min High\n\n"
                f"⏰ {datetime.now(IST).strftime('%H:%M IST')}"
            )
    except Exception:
        pass

# =========================
# MAIN
# =========================
def main():
    now = datetime.now(IST)

    # ---- WEEKDAY CHECK
    if now.weekday() >= 5:
        return

    # ---- MARKET HOURS CHECK
    if now.time() < dtime(9, 30) or now.time() > dtime(15, 30):
        return

    # ---- EXACT 15-MIN SLOT CHECK
    allowed = {0, 15, 30, 45}
    if now.minute not in allowed:
        return

    stock_scores = defaultdict(int)
    stock_sources = defaultdict(list)

    for name, url in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(1)
        for s in stocks:
            stock_scores[s] += 2 if name in ["Volume Shockers", "Price Shockers"] else 1
            stock_sources[s].append(name)

    raw = [
        (s, score, stock_sources[s])
        for s, score in stock_scores.items()
        if score >= 3
    ]

    if not raw:
        send_telegram("⚠ No strong intraday setups at this slot.")
        return

    msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
    for s, score, src in sorted(raw, key=lambda x: x[1], reverse=True)[:10]:
        msg += f"• {s} | Score {score} | {', '.join(src)}\n"

    send_telegram(msg)

    for s, score, _ in raw:
        intraday_transition(s, score)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()
