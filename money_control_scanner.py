import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import time
import pytz
from datetime import datetime
from collections import defaultdict

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

IST = pytz.timezone("Asia/Kolkata")

MAX_UNIVERSE = 40
MAX_BUY_ALERTS = 6
BUY_SCORE_THRESHOLD = 75

# =========================
# MONEYCONTROL APIs (WEIGHTED)
# =========================
APIS = {
    "Volume Shockers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker", 4
    ),
    "Price Shockers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker", 4
    ),
    "Only Buyers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer", 3
    ),
    "Top Gainers": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer", 2
    ),
    "52 Week High": (
        "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high", 1
    ),
}
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
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
    "responseType": "json",
}
# =========================
# UTILITIES
# =========================
def is_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return (
        (now.hour > 9 or (now.hour == 9 and now.minute >= 15))
        and (now.hour < 15 or (now.hour == 15 and now.minute <= 30))
    )


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    requests.post(url, json=payload, timeout=10)


def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        if r.status_code != 200 or not r.text.strip():
            return set()
        data = r.json()
        return {
            item["symbol"]
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except Exception:
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
# INDICATORS
# =========================
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_vwap(df):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

# =========================
# ENTRY VALIDATION (SAFE MODE)
# =========================
def validate_entry(symbol):
    try:
        df = yf.download(
            symbol + ".NS", interval="5m", period="1d", progress=False
        )
        if df.empty or len(df) < 20:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = compute_vwap(df)
        df["VolAvg"] = df["Volume"].rolling(20).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        score = 0
        reasons = []

        # RSI SAFE ZONE
        if 55 <= last["RSI"] <= 65:
            score += 25
            reasons.append("RSI Safe (55–65)")

        # VWAP CONFIRMATION
        if last["Close"] > last["VWAP"] and prev["Close"] <= prev["VWAP"]:
            score += 20
            reasons.append("VWAP Reclaim")

        # VOLUME CONTINUATION (not spike)
        if last["Volume"] > 1.2 * last["VolAvg"] and prev["Volume"] > prev["VolAvg"]:
            score += 20
            reasons.append("Volume Continuation")

        # STRONG CLOSE
        candle_strength = (last["Close"] - last["Low"]) / (
            last["High"] - last["Low"] + 1e-9
        )
        if candle_strength > 0.7:
            score += 15
            reasons.append("Strong Bull Candle")

        # NEAR RECENT HIGH (last 1 hour)
        recent_high = df["High"].rolling(12).max().iloc[-1]
        if last["Close"] >= 0.98 * recent_high:
            score += 20
            reasons.append("Near Intraday High")

        # ENTRY / SL / TARGET
        entry = round(last["Close"], 2)
        sl = round(min(last["Low"], last["VWAP"]) * 0.997, 2)
        target = round(entry + 2 * (entry - sl), 2)

        return {
            "symbol": symbol,
            "price": entry,
            "vwap": round(last["VWAP"], 2),
            "rsi": round(last["RSI"], 1),
            "score": score,
            "entry": entry,
            "sl": sl,
            "target": target,
            "reasons": reasons,
        }

    except Exception:
        return None

# =========================
# MAIN
# =========================
def main():
    #if not is_market_hours():
    #    return

    universe, categories = get_active_universe()

    # RAW MOMENTUM ALERT
    raw_lines = ["📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)"]
    for stock, score in universe[:15]:
        raw_lines.append(
            f"• {stock} | Score {score} | {', '.join(categories[stock])}"
        )

    send_telegram("\n".join(raw_lines))

    # ENTRY VALIDATION
    results = []
    for stock, _ in universe:
        r = validate_entry(stock)
        if r:
            results.append(r)

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    buy_count = 0
    for r in results:
        status = "🟢 BUY" if r["score"] >= BUY_SCORE_THRESHOLD else "🟡 WAIT"

        if status == "🟢 BUY":
            buy_count += 1
            if buy_count > MAX_BUY_ALERTS:
                break

        msg = (
            f"{status} SETUP\n\n"
            f"Stock: {r['symbol']}\n"
            f"Price: {r['price']}\n"
            f"VWAP: {r['vwap']}\n"
            f"RSI(14): {r['rsi']}\n"
            f"Score: {r['score']}/100\n\n"
            f"Entry: {r['entry']}\n"
            f"SL: {r['sl']}\n"
            f"Target: {r['target']}\n\n"
            f"Reasons:\n- " + "\n- ".join(r["reasons"])
        )

        send_telegram(msg)

# =========================
if __name__ == "__main__":
    main()
