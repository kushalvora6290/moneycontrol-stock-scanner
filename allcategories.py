import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, time as dtime
from collections import defaultdict
import pytz

# =========================
# TIMEZONE
# =========================
IST = pytz.timezone("Asia/Kolkata")

def log(msg):
    print(f"[DEBUG] {msg}")

# =========================
# TELEGRAM (GitHub Secrets)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        log("Telegram secrets missing")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
    except Exception as e:
        log(f"Telegram error: {e}")

# =========================
# MONEYCONTROL CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.moneycontrol.com/"
}

COMMON_PARAMS = {
    "deviceType": "W",
    "ex": "N",
    "responseType": "json"
}

APIS = {
    "Top Gainers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer",
    "Only Buyers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer",
    "Price Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker",
    "Volume Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker",
    "52 Week High": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high",
}

WEIGHTS = {
    "Volume Shockers": 3,
    "Price Shockers": 3,
    "Top Gainers": 2,
    "Only Buyers": 1,
    "52 Week High": 1
}

# =========================
# FETCH MONEYCONTROL STOCKS
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

alerted = set()

def intraday_confirmation(stock, score):
    try:
        df = yf.download(stock + ".NS", interval="5m", period="1d", progress=False)
        if df.empty or len(df) < 25:
            return

        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = (
            df["Volume"]
            * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        first_30m = df.between_time("09:15", "09:45")
        if first_30m.empty:
            return

        first_high = first_30m["High"].max()

        conditions = [
            last["Close"] > last["VWAP"],
            last["RSI"] > prev["RSI"],
            55 <= last["RSI"] <= 65,
            last["Close"] > first_high
        ]

        if all(conditions) and stock not in alerted:
            alerted.add(stock)

            send_telegram(
                f"🚨 INTRADAY CONFIRMATION\n\n"
                f"Stock: {stock}\n"
                f"Score: {score}\n"
                f"RSI: {round(last['RSI'],2)}\n"
                f"VWAP: Reclaimed\n"
                f"Breakout: First 30-min High\n\n"
                f"✅ SAFE INTRADAY SETUP"
            )

    except Exception as e:
        log(f"{stock} error: {e}")

# =========================
# MAIN
# =========================
def main():
    now = datetime.now(IST)
    log(f"Running at IST: {now}")

    # Weekdays only
    if now.weekday() >= 5:
        log("Exit: Weekend")
        return

    # Market hours
    if not (dtime(9, 15) <= now.time() <= dtime(15, 30)):
        log("Exit: Outside market hours")
        return

    # Every 15 minutes ONLY
    if now.minute % 15 != 0:
        log("Exit: Not 15-minute candle")
        return

    log("Passed time checks")

    scores = defaultdict(int)
    sources = defaultdict(list)

    for name, url in APIS.items():
        stocks = fetch_stocks(url)
        log(f"{name}: {len(stocks)} stocks")
        time.sleep(1)

        for s in stocks:
            scores[s] += WEIGHTS[name]
            sources[s].append(name)

    raw = [
        (s, scores[s], sources[s])
        for s in scores
        if scores[s] >= 4
    ]

    log(f"Raw momentum count: {len(raw)}")

    if not raw:
        send_telegram("⚠ No strong intraday momentum this slot.")
        return

    msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
    for s, sc, src in sorted(raw, key=lambda x: x[1], reverse=True)[:12]:
        msg += f"• {s} | Score {sc} | {', '.join(src)}\n"

    send_telegram(msg)

    for s, sc, _ in raw:
        intraday_confirmation(s, sc)

if __name__ == "__main__":
    main()
