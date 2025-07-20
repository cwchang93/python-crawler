from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from collections import Counter
import jieba
import yfinance as yf
import pandas as pd
import twstock
from datetime import datetime, timedelta
from datetime import datetime as dt
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

@app.template_filter('datetimeformat')
def datetimeformat(timestamp):
    if not timestamp:
        return ''
    try:
        if isinstance(timestamp, (int, float)):
            timestamp = dt.fromtimestamp(timestamp)
        return timestamp.strftime('%Y-%m-%d %H:%M')
    except:
        return str(timestamp)

def fetch_yahoo_news():
    try:
        url = "https://news.cnyes.com/news/cat/headline"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://news.cnyes.com/'
        }
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, 'lxml')
        news_items = []
        news_elements = soup.select('li.l6okjhz')

        for item in news_elements[:10]:
            title_elem = item.select_one('p.list-title.t2a6dmk a')
            if not title_elem:
                continue
            title = title_elem.get('title', '').strip() or title_elem.get_text(strip=True)
            href = title_elem.get('href', '')

            time_elem = item.select_one('time.n1hj6r9n')
            time_str = time_elem.get_text(strip=True) if time_elem else ''
            try:
                if '-' in time_str and len(time_str.split('-')) == 2:
                    month, day = time_str.split('-')
                    formatted_date = f"{month}-{day}"
                elif ' ' in time_str:
                    date_part = time_str.split(' ')[0]
                    parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                    formatted_date = parsed_date.strftime('%m-%d')
                else:
                    formatted_date = time_str
            except:
                formatted_date = time_str

            category_elem = item.select_one('p.c1m5ajah span')
            category = category_elem.get_text(strip=True) if category_elem else ''

            if title and href:
                if href.startswith('/'):
                    href = f"https://news.cnyes.com{href}"
                news_items.append({
                    'title': title,
                    'link': href,
                    'time': formatted_date,
                    'category': category
                })

        return news_items
    except requests.RequestException as e:
        return []

def extract_keywords(news_items):
    text = "".join([item['title'] for item in news_items])
    words = jieba.lcut(text)
    keywords = [w for w in words if len(w) > 1 and '\u4e00' <= w <= '\u9fff']
    return [word for word, count in Counter(keywords).most_common(10)]

def fetch_news_from_anue_hu(keyword):
    try:
        url = f"https://api.cnyes.com/media/api/v1/newsfeed/search"
        params = {
            'q': keyword,
            'limit': 5,
            'page': 0,
            'type': 'news'
        }
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://news.cnyes.com/'
        }
        response = requests.get(url, headers=headers, params=params, timeout=10, verify=False)
        news_items = []
        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', [])[:5]:
                news_item = {
                    'title': item.get('title', '').strip(),
                    'link': f"https://news.cnyes.com/news/id/{item.get('newsId', '')}",
                    'time': item.get('publishAt', 0)
                }
                if news_item['title'] and news_item['link']:
                    news_items.append(news_item)
        return news_items
    except:
        return []

def fetch_news_by_keyword(keyword):
    news_items = fetch_news_from_anue_hu(keyword)
    if not news_items:
        try:
            url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.news;symbol={keyword}"
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://tw.stock.yahoo.com/'
            }
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('data', [])[:5]:
                    news_item = {
                        'title': item.get('title', '').strip(),
                        'link': item.get('url', '').strip(),
                        'time': item.get('providerPublishTime', 0)
                    }
                    if news_item['title'] and news_item['link']:
                        news_items.append(news_item)
        except:
            pass
    return news_items

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

        stock_name = twstock.codes.get(symbol).name if symbol in twstock.codes else symbol

        return {
            'symbol': symbol,
            'name': stock_name,
            'price': round(today_price, 2),
            'delta_1d': round(delta_1d, 2),
            'delta_7d': round(delta_7d, 2) if delta_7d is not None else None,
            'delta_30d': round(delta_30d, 2),
            'history': hist['Close'].round(2).to_dict()
        }
    except Exception as e:
        print(f"Error analyzing stock {symbol}: {e}")
        return None

def get_hot_stocks():
    hot_symbols = ['2330', '2317', '2303', '2454', '2882', '2603']
    return [analyze_stock(sym) for sym in hot_symbols if analyze_stock(sym)]

@app.route("/", methods=['GET', 'POST'])
def index():
    news = fetch_yahoo_news()
    keywords = extract_keywords(news)
    stock_result = None
    error_message = None
    keyword_news = {keyword: fetch_news_by_keyword(keyword) for keyword in keywords[:3]}

    if request.method == 'POST':
        symbol = request.form.get('symbol')
        if symbol:
            stock_result = analyze_stock(symbol)
            if not stock_result:
                error_message = f"\u627e\u4e0d\u5230\u80a1\u7968\u4ee3\u865f {symbol} \u7684\u8cc7\u6599"

    return render_template(
        "index.html", 
        news=news,
        keywords=keywords,
        keyword_news=keyword_news,
        stock_result=stock_result,
        hot_stocks=get_hot_stocks(),
        error_message=error_message
    )

if __name__ == "__main__":
    app.run(debug=True)