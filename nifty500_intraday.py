import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz

# =====================
# CONFIG
# =====================
BOT_TOKEN = "8133348298:AAGJuwWrqnF_Qu4CSdSpoovnlGU9J0F2aJw"
CHAT_ID = "-5220624919"

IST = pytz.timezone("Asia/Kolkata")

# =====================
# TELEGRAM
# =====================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# =====================
# TIME FILTER
# =====================
def market_time_ok():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return now.hour > 9 or (now.hour == 9 and now.minute >= 15)

# =====================
# RSI
# =====================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =====================
# LOAD NIFTY 500 SYMBOLS
# =====================
def get_nifty500():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    df = pd.read_csv(url)
    return df["Symbol"].tolist()

# =====================
# SCANNER
# =====================
def scan_stock(symbol):
    try:
        df = yf.download(symbol + ".NS", interval="5m", period="1d", progress=False)
        if df.empty or len(df) < 30:
            return None

        df["RSI"] = rsi(df["Close"])
        df["VWAP"] = (df["Volume"] * (df["High"] + df["Low"] + df["Close"]) / 3).cumsum() / df["Volume"].cumsum()
        df["VolAvg"] = df["Volume"].rolling(20).mean()

        last = df.iloc[-1]

        if (
            last["Close"] > last["VWAP"]
            and 55 <= last["RSI"] <= 70
            and last["Volume"] > 1.5 * last["VolAvg"]
            and last["Close"] > last["Open"]
            and (last["Close"] - last["VWAP"]) / last["VWAP"] < 0.02
        ):
            entry = round(last["High"], 2)
            sl = round(last["Low"], 2)
            target = round(entry + 2 * (entry - sl), 2)

            return {
                "symbol": symbol,
                "entry": entry,
                "sl": sl,
                "target": target,
                "rsi": round(last["RSI"], 2),
            }
    except:
        pass
    return None

# =====================
# MAIN
# =====================
def main():
    if not market_time_ok():
        return

    symbols = get_nifty500()
    alerts = []

    for s in symbols:
        result = scan_stock(s)
        if result:
            alerts.append(result)

    if alerts:
        msg = "📊 NIFTY 500 INTRADAY SCANNER (Safe)\n\n"
        for a in alerts[:10]:
            msg += (
                f"🔹 {a['symbol']}\n"
                f"ENTRY: {a['entry']}\n"
                f"SL: {a['sl']}\n"
                f"TARGET: {a['target']}\n"
                f"RSI: {a['rsi']}\n\n"
            )
        send_telegram(msg)
    else:
        send_telegram(
            "📊 NIFTY 500 INTRADAY SCANNER\n\n"
            "⚠ No clean setups right now.\n"
            "➡ Market likely choppy / waiting for expansion."
        )

if __name__ == "__main__":
    main()
