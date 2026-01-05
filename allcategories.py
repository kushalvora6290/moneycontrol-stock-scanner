import os
import time
import requests
import pandas as pd
import yfinance as yf
from collections import defaultdict
from datetime import datetime

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.moneycontrol.com/",
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

# =========================
# CATEGORY WEIGHTS (IMPORTANT)
# =========================
APIS = {
    "Top Gainers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer", 3
    ),
    "Volume Shockers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker", 3
    ),
    "Price Shockers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker", 2
    ),
    "Only Buyers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer", 2
    ),
    "52 Week High": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high", 1
    ),
}

MIN_RAW_SCORE = 5   # replaces len(cats) >= 2

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

# =========================
# UTILS
# =========================
def is_weekday():
    return datetime.now().weekday() < 5  # Mon–Fri

def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# MONEYCONTROL FETCH
# =========================
def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        data = r.json()
        return {
            item["symbol"]
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except:
        return set()

# =========================
# SAFE ENTRY LOGIC
# =========================
def safe_entry_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # RSI safe zone
    if not (55 <= last["RSI"] <= 65):
        return None

    # EMA 20
    ema20 = df["Close"].ewm(span=20).mean().iloc[-1]

    # Price near VWAP / EMA
    if abs(last["Close"] - last["VWAP"]) > 0.3 * last["Close"] / 100 \
       and abs(last["Close"] - ema20) > 0.3 * last["Close"] / 100:
        return None

    # Volume continuation
    avg_vol = df["Volume"].rolling(10).mean().iloc[-2]
    if last["Volume"] < 1.3 * avg_vol:
        return None

    # Strong breakout candle
    body = abs(last["Close"] - last["Open"])
    candle_range = last["High"] - last["Low"]

    if last["Close"] <= prev["High"]:
        return None
    if body < 0.6 * candle_range:
        return None

    entry = round(last["High"], 2)
    sl = round(min(last["Low"], last["VWAP"]), 2)
    target = round(entry + 2 * (entry - sl), 2)

    return entry, sl, target

# =========================
# INTRADAY CHECK
# =========================
alerted = set()

def intraday_transition_alert(stock, score, categories):
    if stock in alerted:
        return

    try:
        df = yf.download(stock + ".NS", interval="5m", period="1d", progress=False)
        if df.empty or len(df) < 30:
            return

        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = (
            df["Volume"]
            * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()

        signal = safe_entry_signal(df)
        if not signal:
            return

        entry, sl, target = signal
        alerted.add(stock)

        send_telegram(
            f"🟢 SAFE INTRADAY SETUP\n\n"
            f"Stock: {stock}\n"
            f"Score: {score}\n"
            f"From: {', '.join(categories)}\n\n"
            f"Entry: {entry}\n"
            f"SL: {sl}\n"
            f"Target: {target}\n\n"
            f"VWAP + RSI + Volume ✔"
        )

    except:
        pass

# =========================
# MAIN
# =========================
def main():
    if not is_weekday():
        return

    stock_data = defaultdict(lambda: {"score": 0, "cats": []})

    # Build RAW momentum (weighted)
    for name, (url, weight) in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(1)
        for s in stocks:
            stock_data[s]["score"] += weight
            stock_data[s]["cats"].append(name)

    raw_list = [
        (s, d["score"], d["cats"])
        for s, d in stock_data.items()
        if d["score"] >= MIN_RAW_SCORE
    ]

    # Send RAW snapshot
    if raw_list:
        msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
        for s, sc, cats in sorted(raw_list, key=lambda x: x[1], reverse=True)[:15]:
            msg += f"• {s} | Score {sc} | {', '.join(cats)}\n"
        send_telegram(msg)

    # Live intraday transition
    for s, sc, cats in raw_list:
        intraday_transition_alert(s, sc, cats)

if __name__ == "__main__":
    main()
