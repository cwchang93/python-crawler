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

app = Flask(__name__)

# Add datetime filter to format timestamps
@app.template_filter('datetimeformat')
def datetimeformat(timestamp):
    if not timestamp:
        return ''
    try:
        # Convert timestamp to datetime object if it's a Unix timestamp
        if isinstance(timestamp, (int, float)):
            timestamp = dt.fromtimestamp(timestamp)
        return timestamp.strftime('%Y-%m-%d %H:%M')
    except:
        return str(timestamp)

def fetch_yahoo_news():
    """Fetch latest stock market news from CNYES"""
    print("\n=== Starting to fetch news from CNYES ===")
    try:
        url = "https://news.cnyes.com/news/cat/headline"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://news.cnyes.com/'
        }
        
        print(f"Making request to: {url}")
        res = requests.get(url, headers=headers, timeout=10)
        print(f"Response status code: {res.status_code}")
        res.raise_for_status()
        
        # Save the response for debugging
        with open('cnyes_response.html', 'w', encoding='utf-8') as f:
            f.write(res.text)
        print("Saved response to cnyes_response.html")
        
        soup = BeautifulSoup(res.text, 'lxml')
        news_items = []
        
        # Find all news items - they are in li elements with class 'l6okjhz'
        news_elements = soup.select('li.l6okjhz')
        print(f"Found {len(news_elements)} news items in the page")
        
        for idx, item in enumerate(news_elements[:10], 1):  # Get top 10 news
            try:
                # Find the title element which is in p.list-title.t2a6dmk > a
                title_elem = item.select_one('p.list-title.t2a6dmk a')
                if not title_elem:
                    print(f"No title element found in item {idx}")
                    continue
                    
                title = title_elem.get('title', '').strip()
                if not title:
                    title = title_elem.get_text(strip=True)
                
                # Get the link
                href = title_elem.get('href', '')
                
                # Get the time and category
                time_elem = item.select_one('time.n1hj6r9n')
                time_str = time_elem.get_text(strip=True) if time_elem else ''
                
                # Try to parse the date from the time string
                try:
                    # If the time_str is in format 'MM-DD', add current year
                    if '-' in time_str and len(time_str.split('-')) == 2:
                        month, day = time_str.split('-')
                        formatted_date = f"{month}-{day}"
                    # If it's a full date string, extract just the date part
                    elif ' ' in time_str:
                        date_part = time_str.split(' ')[0]
                        # Parse and reformat to MM-DD
                        parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                        formatted_date = parsed_date.strftime('%m-%d')
                    else:
                        formatted_date = time_str  # Fallback to original if format is unexpected
                except Exception as e:
                    print(f"Error parsing date: {e}")
                    formatted_date = time_str  # Fallback to original if parsing fails
                
                category_elem = item.select_one('p.c1m5ajah span')
                category = category_elem.get_text(strip=True) if category_elem else ''
                
                print(f"\n--- Processing item {idx} ---")
                print(f"Title: {title}")
                print(f"Date: {formatted_date}")
                print(f"Category: {category}")
                print(f"Href: {href}")
                
                # Make sure we have both title and link
                if title and href:
                    # Convert relative URL to absolute if needed
                    if href.startswith('/'):
                        href = f"https://news.cnyes.com{href}"
                    
                    news_items.append({
                        'title': title,
                        'link': href,
                        'time': formatted_date,  # Only date in MM-DD format
                        'category': category
                    })
                    print("✓ Added to news items")
                else:
                    print("✗ Missing title or href")
                    
            except Exception as e:
                print(f"Error processing news item {idx}: {e}")
                print(f"Item HTML: {str(item)[:200]}...")
                continue
        
        print(f"\n=== Successfully fetched {len(news_items)} news items ===")
        for idx, item in enumerate(news_items, 1):
            print(f"{idx}. [{item.get('category', '')}] {item['title']}")
            print(f"   {item['link']}")
                
        return news_items
        
    except requests.RequestException as e:
        print(f"Error fetching news from CNYES: {e}")
        if 'res' in locals():
            print(f"Response content: {res.text[:500]}...")
        # Fallback to empty list if there's an error
        return []

def extract_keywords(news_items):
    text = "".join([item['title'] for item in news_items])
    words = jieba.lcut(text)
    # Filter out common words and keep only Chinese words
    keywords = [w for w in words if len(w) > 1 and '\u4e00' <= w <= '\u9fff']
    return [word for word, count in Counter(keywords).most_common(10)]

def fetch_news_from_anue_hu(keyword):
    """Fetch news from Anue (鉅亨網) with better compatibility"""
    try:
        print(f"Trying to fetch news from Anue for keyword: {keyword}")
        url = f"https://api.cnyes.com/media/api/v1/newsfeed/search"
        params = {
            'q': keyword,
            'limit': 5,
            'page': 0,
            'type': 'news'
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://news.cnyes.com/'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        news_items = []
        
        if response.status_code == 200:
            data = response.json()
            print(f"Successfully fetched {len(data.get('items', []))} news items from Anue")
            for item in data.get('items', [])[:5]:
                try:
                    news_item = {
                        'title': item.get('title', '').strip(),
                        'link': f"https://news.cnyes.com/news/id/{item.get('newsId', '')}",
                        'time': item.get('publishAt', 0)
                    }
                    if news_item['title'] and news_item['link']:
                        news_items.append(news_item)
                        print(f"Added news: {news_item['title']}")
                except Exception as e:
                    print(f"Error processing Anue news item: {e}")
        else:
            print(f"Anue API returned status code: {response.status_code}")
            
        return news_items
        
    except Exception as e:
        print(f"Error in fetch_news_from_anue_hu: {str(e)}")
        return []

def fetch_news_by_keyword(keyword):
    """Fetch news related to a specific keyword with better error handling and data validation"""
    print(f"\n=== Fetching news for keyword: {keyword} ===")
    
    # Try Anue (鉅亨網) first
    news_items = fetch_news_from_anue_hu(keyword)
    
    # If no news from Anue, try Yahoo Finance TW
    if not news_items:
        print(f"No news from Anue, trying Yahoo Finance for keyword: {keyword}")
        try:
            url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.news;symbol={keyword}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://tw.stock.yahoo.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Yahoo Finance response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Found {len(data.get('data', []))} news items in Yahoo Finance")
                for item in data.get('data', [])[:5]:
                    try:
                        news_item = {
                            'title': item.get('title', '').strip(),
                            'link': item.get('url', '').strip(),
                            'time': item.get('providerPublishTime', 0)
                        }
                        if news_item['title'] and news_item['link']:
                            news_items.append(news_item)
                            print(f"Added news: {news_item['title']}")
                    except Exception as e:
                        print(f"Error processing Yahoo news item: {e}")
        except Exception as e:
            print(f"Error fetching from Yahoo Finance: {e}")
    
    print(f"Total news items found for {keyword}: {len(news_items)}")
    return news_items

def analyze_stock(symbol):
    try:
        # Get stock info using twstock
        stock = twstock.Stock(symbol)
        
        # Get the stock's Chinese name
        stock_name = stock.sid  # Default to symbol
        try:
            stock_name = twstock.realtime.get(symbol)['info']['name']
        except:
            pass  # If we can't get the name, just use the symbol
            
        # Get historical data using yfinance for price and calculations
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
    hot_data = []
    for sym in hot_symbols:
        result = analyze_stock(sym)
        if result:
            hot_data.append(result)
    return hot_data

@app.route("/", methods=['GET', 'POST'])
def index():
    print("\n=== Starting new request ===")
    news = fetch_yahoo_news()
    print(f"Fetched {len(news)} news items from Yahoo")
    
    keywords = extract_keywords(news)
    print(f"Extracted keywords: {keywords}")
    
    stock_result = None
    error_message = None
    keyword_news = {}

    # Get news for each keyword
    for keyword in keywords[:3]:  # Limit to top 3 keywords to avoid too many requests
        print(f"\nProcessing keyword: {keyword}")
        keyword_news[keyword] = fetch_news_by_keyword(keyword)
        print(f"Found {len(keyword_news[keyword])} news items for keyword: {keyword}")

    if request.method == 'POST':
        symbol = request.form.get('symbol')
        if symbol:
            print(f"\n=== Fetching data for symbol: {symbol} ===")
            stock_result = analyze_stock(symbol)
            print("=== Raw stock_result ===")
            print(stock_result)
            if not stock_result:
                error_message = f"找不到股票代號 {symbol} 的資料"

    hot_stocks = get_hot_stocks()
    print("\n=== Rendering template ===")
    print(f"Keywords with news: {list(keyword_news.keys())}")
    for keyword, items in keyword_news.items():
        print(f"- {keyword}: {len(items)} items")
    
    return render_template(
        "index.html", 
        news=news, 
        keywords=keywords, 
        keyword_news=keyword_news,
        stock_result=stock_result, 
        hot_stocks=hot_stocks, 
        error_message=error_message
    )

if __name__ == "__main__":
    app.run(debug=True)
