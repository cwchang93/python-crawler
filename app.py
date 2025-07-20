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
import os
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Set the backend to 'Agg' to avoid GUI issues
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure static directory exists for saving plots
os.makedirs('static/plots', exist_ok=True)

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

def generate_stock_plots(symbol, hist):
    """Generate stock analysis plots and save them as static files"""
    try:
        plt.figure(figsize=(12, 6))
        plt.plot(hist.index, hist['Close'], label='Close', color='#1f77b4', linewidth=2)
        plt.plot(hist.index, hist['MA5'], label='5-day MA', linestyle='--', color='#ff7f0e')
        plt.plot(hist.index, hist['MA10'], label='10-day MA', linestyle='--', color='#2ca02c')
        
        plt.title(f'{symbol} Stock Price Trend')
        plt.ylabel('Price (TWD)')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Format x-axis
        date_format = DateFormatter('%m-%d')
        plt.gca().xaxis.set_major_formatter(date_format)
        plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save the plot
        plot_filename = f'stock_plot_{symbol}.png'
        plot_path = os.path.join('static', 'plots', plot_filename)
        plt.savefig(plot_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        return plot_filename
    except Exception as e:
        print(f"Error generating stock plot: {e}")
        return None

def analyze_stock(symbol):
    try:
        # Get stock data
        ticker = yf.Ticker(f"{symbol}.TW")
        hist = ticker.history(period="1mo", interval="1d")        

        if hist.empty:
            return None
        
        # Calculate basic statistics
        close_prices = hist['Close']
        volumes = hist['Volume']
        
        # Calculate moving averages
        hist['MA5'] = close_prices.rolling(window=5).mean()
        hist['MA10'] = close_prices.rolling(window=10).mean()
        
        # Calculate daily returns
        hist['Daily_Return'] = close_prices.pct_change() * 100
        
        # Find max gain and max drop days
        max_gain_idx = hist['Daily_Return'].idxmax()
        max_drop_idx = hist['Daily_Return'].idxmin()
        
        # Calculate statistics
        avg_close = close_prices.mean()
        std_close = close_prices.std()
        total_volume = volumes.sum()
        avg_volume = volumes.mean()
        
        # Generate plots
        plot_filename = generate_stock_plots(symbol, hist)
        
        # Get stock name
        stock_name = twstock.codes.get(symbol).name if symbol in twstock.codes else symbol
        
        # Prepare analysis summary
        analysis_summary = {
            'symbol': symbol,
            'name': stock_name,
            'current_price': close_prices.iloc[-1],
            'avg_close': avg_close,
            'std_close': std_close,
            'volatility': (std_close / avg_close) * 100,  # Volatility as percentage
            'max_gain': hist['Daily_Return'].max(),
            'max_gain_date': max_gain_idx.strftime('%Y-%m-%d'),
            'max_drop': hist['Daily_Return'].min(),
            'max_drop_date': max_drop_idx.strftime('%Y-%m-%d'),
            'total_volume': total_volume,
            'avg_volume': avg_volume,
            'ma5': hist['MA5'].iloc[-1],
            'ma10': hist['MA10'].iloc[-1],
            'plot_filename': plot_filename,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return analysis_summary
        
    except Exception as e:
        print(f"Error analyzing stock {symbol}: {e}")
        return None

def get_hot_stocks():
    hot_symbols = ['2330', '2317', '2303', '2454', '2882', '2603']
    hot_stocks = []
    for sym in hot_symbols:
        stock_data = analyze_stock(sym)
        if stock_data:
            # Only include essential data for the hot stocks table
            hot_stocks.append({
                'symbol': stock_data['symbol'],
                'name': stock_data['name'],
                'price': round(stock_data['current_price'], 2),
                'delta_1d': round((stock_data['current_price'] - stock_data['avg_close']) / stock_data['avg_close'] * 100, 2),
                'delta_7d': None,  # Not calculated in the new analysis
                'delta_30d': round(stock_data['volatility'], 2)
            })
    return hot_stocks

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