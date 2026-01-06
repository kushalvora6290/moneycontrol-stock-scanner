import time
import requests
import yfinance as yf
import pandas as pd
from collections import defaultdict
from datetime import datetime
import pytz

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

MAX_UNIVERSE = 50
MAX_BUY_ALERTS = 25
SLEEP_BETWEEN_CALLS = 0.7

IST = pytz.timezone("Asia/Kolkata")

# =========================
# MONEYCONTROL (UNCHANGED)
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
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# =========================
# INDICATORS
# =========================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# UNIVERSE
# =========================
def get_active_universe():
    score = defaultdict(int)
    cats = defaultdict(list)

    for name, (url, w) in APIS.items():
        try:
            r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
            data = r.json().get("data", {}).get("list", [])
            for i in data:
                s = i.get("symbol")
                if s:
                    score[s] += w
                    cats[s].append(name)
            time.sleep(SLEEP_BETWEEN_CALLS)
        except:
            pass

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:MAX_UNIVERSE]
    return ranked, cats

# =========================
# ENTRY VALIDATION (SAFE MODE)
# =========================
def validate_entry(stock):
    df = yf.download(
    stock + ".NS",
    interval="5m",
    period="1d",
    progress=False,
    threads=False,
    timeout=20
)



    if df is None or df.empty or len(df) < 40:
        return None

    # 🔥 FIX MULTIINDEX
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["RSI"] = rsi(df["Close"])
    df["VolAvg"] = df["Volume"].rolling(20).mean()

    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

    prev = df.iloc[-2]
    last = df.iloc[-1]

    # FORCE SCALARS
    last_close = float(last["Close"])
    last_open  = float(last["Open"])
    last_high  = float(last["High"])
    last_low   = float(last["Low"])
    last_vwap  = float(last["VWAP"])
    last_vol   = float(last["Volume"])
    avg_vol    = float(last["VolAvg"])
    last_rsi   = float(last["RSI"])
    prev_rsi   = float(prev["RSI"])

    score = 0

    if last_close > last_vwap:
        score += 20

    if float(prev["Close"]) < float(prev["VWAP"]) and last_close > last_vwap:
        score += 20

    if 55 <= last_rsi <= 65 and last_rsi > prev_rsi:
        score += 15

    if last_vol > 1.3 * avg_vol:
        score += 15

    if last_close > last_open:
        score += 15

    if last_close > 0.9 * df["High"].max():
        score += 15

    entry = round(last_high, 2)
    sl = round(last_low, 2)
    target = round(entry + 2 * (entry - sl), 2)

    status = "🟢 BUY" if score >= 70 else "🟡 WAIT"

    return {
        "stock": stock,
        "score": score,
        "status": status,
        "entry": entry,
        "sl": sl,
        "target": target,
        "rsi": round(last_rsi, 2),
        "vwap": round(last_vwap, 2),
    }
    
# =========================
# MAIN
# =========================
def main():
    universe, cats = get_active_universe()

    # RAW MOMENTUM
    raw = "📊 Moneycontrol Momentum (RAW)\n\n"
    for s, sc in universe:
        raw += f"• {s} | Score {sc}\n"
    send_telegram(raw)

    # VALIDATED SETUPS
    buys = []
    for s, _ in universe:
        res = validate_entry(s)
        if res:
            buys.append(res)

    buys = sorted(buys, key=lambda x: x["score"], reverse=True)[:MAX_BUY_ALERTS]

    for b in buys:
        send_telegram(
            f"{b['status']} SETUP FOUND\n\n"
            f"Stock: {b['stock']}\n"
            f"Price: {b['entry']}\n"
            f"VWAP: {b['vwap']}\n"
            f"RSI(14): {b['rsi']}\n"
            f"Score: {b['score']}/100\n\n"
            f"Entry: {b['entry']}\n"
            f"SL: {b['sl']}\n"
            f"Target: {b['target']}\n\n"
            f"Structure: Bullish Continuation"
        )

if __name__ == "__main__":
    main()

