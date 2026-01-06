import os
import time
import requests
import pandas as pd
import yfinance as yf
from collections import defaultdict
from datetime import datetime
import pytz

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

MAX_UNIVERSE = 120

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)

# =========================
# TIME CHECK
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
# TECHNICALS
# =========================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
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
            item.get("symbol")
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except:
        return set()

# =========================
# BUILD ACTIVE UNIVERSE
# =========================
def get_active_universe():
    scores = defaultdict(int)
    categories = defaultdict(list)

    for name, (url, weight) in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(0.8)
        for s in stocks:
            scores[s] += weight
            categories[s].append(name)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    universe = ranked[:MAX_UNIVERSE]

    return universe, categories

# =========================
# INTRADAY CHECK
# =========================
def intraday_check(stock):
    try:
        df = yf.download(
            stock + ".NS",
            interval="1m",
            period="1d",
            progress=False
        )

        # keep only last 60 minutes
        df = df.tail(60)

        if df.empty or len(df) < 30:
            return None

        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = (
            df["Volume"]
            * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()
        df["VolAvg"] = df["Volume"].rolling(20).mean()

        last = df.iloc[-1]

        if (
            last["Close"] > last["VWAP"]
            and 55 <= last["RSI"] <= 70
            and last["Volume"] > 1.3 * last["VolAvg"]
            and last["Close"] > last["Open"]
        ):
            entry = round(last["High"], 2)
            sl = round(last["Low"], 2)
            target = round(entry + 2 * (entry - sl), 2)

            return entry, sl, target, round(last["RSI"], 2)

    except:
        pass

    return None

# =========================
# MAIN
# =========================
def main():
    if not market_time_ok():
        return

    universe, categories = get_active_universe()

    if not universe:
        send_telegram(
            "📊 Intraday Scanner\n\n⚠ No active stocks from Moneycontrol."
        )
        return

    # ---- RAW SNAPSHOT
    msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
    for s, score in universe[:10]:
        cats = ", ".join(categories[s])
        msg += f"• {s} | Score {score} | {cats}\n"
    send_telegram(msg)

    # ---- INTRADAY CONFIRMATION
    alerts = []

    for s, score in universe:
        result = intraday_check(s)
        if result:
            entry, sl, target, rsi = result
            alerts.append((s, score, entry, sl, target, rsi))

    if alerts:
        msg = "🚨 INTRADAY ACTIONABLE SETUPS\n\n"
        for s, score, e, sl, t, rsi in alerts[:5]:
            msg += (
                f"🔹 {s}\n"
                f"Score: {score}\n"
                f"Entry: {e}\n"
                f"SL: {sl}\n"
                f"Target: {t}\n"
                f"RSI: {rsi}\n\n"
            )
        send_telegram(msg)
    else:
        send_telegram(
            "⚠ No clean intraday setups yet.\n➡ Market likely choppy / waiting."
        )

if __name__ == "__main__":
    main()
