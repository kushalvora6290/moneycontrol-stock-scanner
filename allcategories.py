import os
import time
import requests
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
# TECHNICAL HELPERS
# =========================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Prevent duplicate alerts per day
alerted_trade_ready = set()

# =========================
# INTRADAY LOGIC
# =========================
def intraday_check(stock, score):
    try:
        df = yf.download(stock + ".NS", interval="5m", period="1d", progress=False)
        if df.empty or len(df) < 20:
            return

        # Indicators
        df["RSI"] = compute_rsi(df["Close"])
        df["VWAP"] = (
            df["Volume"] * (df["High"] + df["Low"] + df["Close"]) / 3
        ).cumsum() / df["Volume"].cumsum()
        df["VOL_AVG"] = df["Volume"].rolling(20).mean()

        price = df.iloc[-1]["Close"]
        vwap = df.iloc[-1]["VWAP"]
        rsi_now = df["RSI"].iloc[-1]
        rsi_prev = df["RSI"].iloc[-2]
        vol_now = df.iloc[-1]["Volume"]
        vol_avg = df.iloc[-1]["VOL_AVG"]

        # First 30-min range
        first_30 = df.between_time("09:15", "09:45")
        if first_30.empty:
            return
        first_high = first_30["High"].max()

        # =========================
        # 🟡 TIER-1: EARLY MOMENTUM
        # =========================
        if (
            abs(price - vwap) / vwap <= 0.003
            and rsi_now > rsi_prev
            and vol_now > vol_avg
        ):
            send_telegram(
                f"🟡 EARLY MOMENTUM\n\n"
                f"{stock}\n"
                f"Score: {score}\n"
                f"RSI: {round(rsi_now, 2)}\n"
                f"Price near VWAP\n"
                f"Volume building\n\n"
                f"👀 Watch for breakout"
            )

        # =========================
        # 🔴 TIER-2: TRADE READY
        # =========================
        if (
            stock not in alerted_trade_ready
            and price >= vwap * 0.998
            and price >= first_high * 0.995
            and 50 <= rsi_now <= 75
            and rsi_now > rsi_prev
            and vol_now > vol_avg
        ):
            alerted_trade_ready.add(stock)

            send_telegram(
                f"🚨 TRADE READY\n\n"
                f"{stock}\n"
                f"Score: {score}\n"
                f"RSI: {round(rsi_now, 2)}\n"
                f"VWAP: Reclaimed\n"
                f"30-min range pressure\n\n"
                f"✅ Actionable setup"
            )

    except Exception:
        pass

# =========================
# MAIN
# =========================
def main():
    now = datetime.now(IST)

    # Weekday only
    if now.weekday() >= 5:
        return

    # Market hours only
    if now.time() < dtime(9, 15) or now.time() > dtime(15, 30):
        return

    # 15-minute slots only
    if now.minute not in {0, 15, 30, 45}:
        return

    # -------------------------
    # BUILD RAW MOMENTUM
    # -------------------------
    stock_scores = defaultdict(int)
    stock_sources = defaultdict(list)

    for name, url in APIS.items():
        stocks = fetch_stocks(url)
        time.sleep(1)
        for s in stocks:
            weight = 2 if name in ["Volume Shockers", "Price Shockers"] else 1
            stock_scores[s] += weight
            stock_sources[s].append(name)

    raw = [
        (s, score, stock_sources[s])
        for s, score in stock_scores.items()
        if score >= 3
    ]

    if not raw:
        send_telegram("⚠ No strong intraday momentum at this slot.")
        return

    # -------------------------
    # SEND RAW SNAPSHOT
    # -------------------------
    msg = "📊 Moneycontrol Intraday Scanner\n\n🔹 MARKET MOMENTUM (Raw)\n"
    for s, score, src in sorted(raw, key=lambda x: x[1], reverse=True)[:10]:
        msg += f"• {s} | Score {score} | {', '.join(src)}\n"
    send_telegram(msg)

    # -------------------------
    # CHECK INTRADAY SETUPS
    # -------------------------
    for s, score, _ in raw:
        intraday_check(s, score)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()
