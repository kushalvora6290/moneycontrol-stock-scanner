import requests
import pandas as pd
import yfinance as yf
import numpy as np
from collections import defaultdict

# ================= TELEGRAM CONFIG =================
BOT_TOKEN = "8133348298:AAGJuwWrqnF_Qu4CSdSpoovnlGU9J0F2aJw"
CHAT_ID = "-5220624919"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    r = requests.post(url, json=payload)
    return r.json()

# ================= MONEYCONTROL CONFIG =================
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

APIS = {
    "Top Gainers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/gainer",
    "Only Buyers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/buyer",
    "Price Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/price-shocker",
    "Volume Shockers": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/volume-shocker",
    "52 Week High": "https://api.moneycontrol.com/swiftapi/v1/markets/stats/52-week-high"
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

# ================= FUNCTIONS =================
def fetch_stocks(url):
    try:
        r = requests.get(url, headers=HEADERS, params=COMMON_PARAMS, timeout=10)
        r.raise_for_status()
        data = r.json()

        return {
            item.get("symbol")
            for item in data.get("data", {}).get("list", [])
            if item.get("symbol")
        }
    except Exception as e:
        print("❌ API Error:", e)
        return set()


def calculate_rsi(symbol, period=14):
    try:
        ticker = yf.Ticker(symbol + ".NS")
        hist = ticker.history(period="2mo")

        if hist.empty or len(hist) < period:
            return None

        delta = hist["Close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi.iloc[-1], 2)
    except:
        return None

# ================= MAIN =================
def main():
    stock_occurrence = defaultdict(list)

    print("\n📊 FETCHING MONEYCONTROL DATA\n")

    for category, url in APIS.items():
        stocks = fetch_stocks(url)
        for stock in stocks:
            stock_occurrence[stock].append(category)
        print(f"✅ {category}: {len(stocks)} stocks")

    # Stocks in 2+ categories
    multi_common = {
        stock: cats
        for stock, cats in stock_occurrence.items()
        if len(cats) >= 2
    }

    rows = []
    telegram_msg = "📊 Moneycontrol Scanner Alert\n\n"

    for stock, cats in multi_common.items():
        rsi = calculate_rsi(stock)
        strength = round(len(cats) * rsi, 2) if rsi else 0
        
        rows.append({
            "Stock": stock,
            "Categories": ", ".join(cats),
            "Category Count": len(cats),
            "RSI(14)": rsi,
            "Strength Score": strength
        })

        telegram_msg += (
            f"🔹 {stock}\n"
            f"   Categories: {len(cats)}\n"
            f"   RSI(14): {rsi}\n\n"
        )

    # Export CSV
    #df = pd.DataFrame(rows).sort_values(
    #    by=["Category Count", "RSI(14)"],
    #    ascending=[False, True]
    #)
    
    df = pd.DataFrame(rows)

    df = df.sort_values(
        by="Strength Score",
        ascending=False
    )

    top_3 = df.head(3)
    
    telegram_msg_top3 = "🔥 TOP 3 STRONGEST STOCKS \n\n"

    for _, row in top_3.iterrows():
        telegram_msg_top3 += (
            f"🏆 {row['Stock']}\n"
            f"Categories: {row['Category Count']}\n"
            f"RSI(14): {row['RSI(14)']}\n"
            f"Strength: {row['Strength Score']}\n\n"
        )
    
    output_file = "moneycontrol_scanner_with_RSI.csv"
    df.to_csv(output_file, index=False)
    print(f"\n📁 CSV Exported: {output_file}")

    # Send Telegram alert
    if rows:
        response = send_telegram_message(telegram_msg)
       
        print("📩 Telegram Response:", response)
        
        response_top3 = send_telegram_message(telegram_msg_top3)
       
        print("📩 Telegram Response:", response_top3)
    else:
        print("ℹ️ No stocks qualified for Telegram alert")

if __name__ == "__main__":
    main()
