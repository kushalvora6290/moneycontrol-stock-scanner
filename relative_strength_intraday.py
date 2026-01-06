import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8133348298:AAGJuwWrqnF_Qu4CSdSpoovnlGU9J0F2aJw"
CHAT_ID = "-5220624919"

IST = pytz.timezone("Asia/Kolkata")

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

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
# RSI
# =========================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# LOAD NIFTY 500
# =========================
def get_nifty500():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    df = pd.read_csv(url)
    return df["Symbol"].tolist()

# =========================
# MAIN
# =========================
def main():
    if not market_time_ok():
        return

    # ---- NIFTY performance
    nifty = yf.download("^NSEI", interval="5m", period="1d", progress=False)
    if nifty.empty:
        return

    nifty_pct = (
        (nifty["Close"].iloc[-1] - nifty["Open"].iloc[0])
        / nifty["Open"].iloc[0]
    ) * 100

    alerts = []
    symbols = get_nifty500()

    for s in symbols:
        try:
            df = yf.download(s + ".NS", interval="5m", period="1d", progress=False)
            if df.empty or len(df) < 30:
                continue

            df["RSI"] = rsi(df["Close"])
            df["VWAP"] = (
                df["Volume"]
                * (df["High"] + df["Low"] + df["Close"]) / 3
            ).cumsum() / df["Volume"].cumsum()
            df["VolAvg"] = df["Volume"].rolling(20).mean()

            last = df.iloc[-1]

            stock_pct = (
                (last["Close"] - df["Open"].iloc[0])
                / df["Open"].iloc[0]
            ) * 100

            if (
                stock_pct > nifty_pct
                and last["Close"] > last["VWAP"]
                and last["Volume"] > 1.3 * last["VolAvg"]
                and last["RSI"] > 55
                and last["Close"] > last["Open"]
            ):
                alerts.append((s, round(stock_pct, 2), round(last["RSI"], 2)))

        except:
            continue

    if alerts:
        msg = "📊 RELATIVE STRENGTH SCANNER (Intraday)\n\n"
        for s, pct, r in alerts[:10]:
            msg += (
                f"• {s}\n"
                f"  Stock %: +{pct}%\n"
                f"  RSI: {r}\n"
                f"  ➡ Market-beating momentum\n\n"
            )
        send_telegram(msg)
    else:
        send_telegram(
            "📊 RELATIVE STRENGTH SCANNER\n\n"
            "⚠ No stocks outperforming NIFTY right now."
        )

if __name__ == "__main__":
    main()
