import yfinance as yf
import pandas as pd
import requests
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import os
import pandas as pd

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# =========================
# LOAD SYMBOLS (CACHED)
# =========================
def load_symbols():
    CACHE_FILE = "nse_symbols.csv"

    # 1️⃣ Try cache first
    if os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE)
        for col in df.columns:
            if col.lower() == "symbol":
                return df[col].dropna().tolist()

        # Corrupt cache → delete
        os.remove(CACHE_FILE)

    # 2️⃣ Download fresh from NSE
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    df = pd.read_csv(url)

    # Normalize column names
    df.columns = [c.strip().upper() for c in df.columns]

    # Detect required columns
    if "SYMBOL" not in df.columns:
        raise Exception("❌ SYMBOL column not found in NSE file")

    # SERIES column is optional now
    if "SERIES" in df.columns:
        df = df[df["SERIES"] == "EQ"]

    symbols = df["SYMBOL"].astype(str).apply(lambda x: f"{x}.NS").tolist()

    # Save cache
    pd.DataFrame({"symbol": symbols}).to_csv(CACHE_FILE, index=False)

    print(f"✅ NSE symbols loaded: {len(symbols)}")

    return symbols
# =========================
# MAIN
# =========================
def main():
    symbols = load_symbols()
    print(f"Symbols: {len(symbols)}")

    # 🔥 BULK DOWNLOAD
    data = yf.download(
        symbols,
        period="3mo",
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False
    )

    alerts = []

    for sym in symbols:
        try:
            df = data[sym].dropna()
            if len(df) < 30:
                continue

            l = df.iloc[-1]
            p = df.iloc[-2]

            # Stage-0 (ultra fast)
            if not (100 <= l["Close"] <= 3000):
                continue
            if l["Volume"] < df["Volume"].rolling(20).mean().iloc[-1]:
                continue

            # Trend
            ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
            ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
            if not (l["Close"] > ema20 > ema50):
                continue

            # Momentum
            rsi = RSIIndicator(df["Close"], 14).rsi().iloc[-1]
            if not (55 <= rsi <= 70):
                continue

            # Breakout
            if l["Close"] <= df["High"].rolling(5).max().iloc[-2]:
                continue

            # ATR
            atr = AverageTrueRange(df["High"], df["Low"], df["Close"], 14).average_true_range().iloc[-1]

            entry = round(l["High"], 2)
            target = round(max(entry * 1.05, entry + 2 * atr), 2)
            sl = round(entry - atr, 2)

            alerts.append({
                "symbol": sym.replace(".NS", ""),
                "entry": entry,
                "target": target,
                "sl": sl,
                "rsi": round(rsi, 1)
            })

        except:
            continue

    for a in alerts:
        msg = f"""
📈 *FAST 5% SWING ALERT*

{a['symbol']}
Entry: ₹{a['entry']}
Target: ₹{a['target']}
SL: ₹{a['sl']}
RSI: {a['rsi']}
Timeframe: 3–7 Days
        """
        send_telegram(msg)

    print(f"Alerts: {len(alerts)}")

if __name__ == "__main__":
    main()
