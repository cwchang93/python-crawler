from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
from collections import Counter
import jieba
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

def fetch_yahoo_news():
    url = "https://tw.stock.yahoo.com/"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    news_items = []

    for item in soup.select('a[data-ylk*="t1:a1"]')[:10]:
        title = item.text.strip()
        link = "https://tw.stock.yahoo.com" + item['href']
        news_items.append({'title': title, 'link': link})
    return news_items

def extract_keywords(news_items):
    text = "".join([item['title'] for item in news_items])
    words = jieba.lcut(text)
    keywords = [w for w in words if len(w) > 1]
    return Counter(keywords).most_common(10)

def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        hist = ticker.history(period="1mo")
        if hist.empty:
            return None

        today_price = hist.iloc[-1]['Close']
        delta_1d = (hist.iloc[-1]['Close'] - hist.iloc[-2]['Close']) / hist.iloc[-2]['Close'] * 100
        delta_7d = (hist.iloc[-1]['Close'] - hist.iloc[-6]['Close']) / hist.iloc[-6]['Close'] * 100 if len(hist) >= 7 else None
        delta_30d = (hist.iloc[-1]['Close'] - hist.iloc[0]['Close']) / hist.iloc[0]['Close'] * 100

        return {
            'symbol': symbol,
            'price': round(today_price, 2),
            'delta_1d': round(delta_1d, 2),
            'delta_7d': round(delta_7d, 2) if delta_7d else None,
            'delta_30d': round(delta_30d, 2),
            'history': hist['Close'].round(2).to_dict()
        }
    except:
        return None

def get_hot_stocks():
    hot_symbols = ['2330', '2317', '2303', '2454', '2882', '2603']
    hot_data = []
    for sym in hot_symbols:
        result = analyze_stock(sym)
        if result:
            hot_data.append(result)
    return hot_data

@app.route("/", methods=['GET', 'POST'])
def index():
    news = fetch_yahoo_news()
    keywords = extract_keywords(news)
    stock_result = None
    error_message = None

    if request.method == 'POST':
        symbol = request.form.get('symbol')
        if symbol:
            stock_result = analyze_stock(symbol)
            if not stock_result:
                error_message = f"找不到股票代號 {symbol} 的資料"

    hot_stocks = get_hot_stocks()
    return render_template("index.html", news=news, keywords=keywords, stock_result=stock_result, hot_stocks=hot_stocks, error_message=error_message)

if __name__ == "__main__":
    app.run(debug=True)
