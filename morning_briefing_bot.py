#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 每日早报推送机器人
功能：每天早上8点自动推送 AI资讯 + 美股行情 + 加密货币价格
"""

import os
import time
import schedule
import requests
import feedparser
from datetime import datetime, timedelta

# ============== 配置区域 ==============
# Telegram 配置
TELEGRAM_BOT_TOKEN = os.getenv("8286090935:AAGaqLddlJBiPZ_wxsMm_OxrPRBO7JBfqiI", "你的Bot Token")
TELEGRAM_CHAT_ID = os.getenv("6260452650", "你的Chat ID")

# 推送时间（24小时制）
PUSH_TIME = "08:00"

# 时区设置（Asia/Shanghai = UTC+8）
TIMEZONE_OFFSET = 8

# ============== AI 资讯模块 ==============
AI_RSS_FEEDS = [
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/"
    },
    {
        "name": "MIT Tech Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"
    },
]

def fetch_ai_news(max_per_source=3):
    """抓取AI相关RSS新闻"""
    news_list = []
    yesterday = datetime.utcnow() - timedelta(days=1)

    for feed_info in AI_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries:
                if count >= max_per_source:
                    break
                # 尝试过滤24小时内的新闻
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_time = datetime(*published[:6])
                    if pub_time < yesterday:
                        continue

                title = entry.get("title", "无标题")
                link = entry.get("link", "")
                news_list.append({
                    "source": feed_info["name"],
                    "title": title,
                    "link": link
                })
                count += 1
        except Exception as e:
            print(f"[RSS Error] {feed_info['name']}: {e}")

    return news_list


def format_ai_news(news_list):
    """格式化AI新闻"""
    if not news_list:
        return "暂无最新AI资讯\n"

    text = ""
    for i, news in enumerate(news_list, 1):
        text += f"  {i}. [{news['title']}]({news['link']})\n"
        text += f"     📌 来源: {news['source']}\n"
    return text


# ============== 美股行情模块 ==============
US_STOCK_SYMBOLS = {
    "^GSPC": "标普500",
    "^IXIC": "纳斯达克",
    "^DJI": "道琼斯",
    "AAPL": "苹果",
    "MSFT": "微软",
    "NVDA": "英伟达",
    "GOOGL": "谷歌",
    "TSLA": "特斯拉",
    "META": "Meta",
    "AMZN": "亚马逊",
}


def fetch_us_stocks():
    """通过Yahoo Finance获取美股数据"""
    results = []
    symbols = ",".join(US_STOCK_SYMBOLS.keys())

    try:
        # 使用Yahoo Finance v8 API
        url = f"https://query1.finance.yahoo.com/v8/finance/spark"
        params = {
            "symbols": symbols,
            "range": "1d",
            "interval": "1d",
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            for symbol, name in US_STOCK_SYMBOLS.items():
                try:
                    spark = data["spark"]["result"]
                    for item in spark:
                        if item["symbol"] == symbol:
                            meta = item["response"][0]["meta"]
                            price = meta.get("regularMarketPrice", 0)
                            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose", 0)
                            if prev_close and prev_close > 0:
                                change_pct = ((price - prev_close) / prev_close) * 100
                            else:
                                change_pct = 0
                            emoji = "🟢" if change_pct >= 0 else "🔴"
                            results.append({
                                "name": name,
                                "symbol": symbol,
                                "price": price,
                                "change_pct": change_pct,
                                "emoji": emoji
                            })
                            break
                except Exception:
                    pass
    except Exception as e:
        print(f"[Stock Error] {e}")

    # 备用方案：使用另一个免费API
    if not results:
        results = fetch_us_stocks_backup()

    return results


def fetch_us_stocks_backup():
    """备用方案获取股票数据"""
    results = []
    for symbol, name in US_STOCK_SYMBOLS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
            params = {"modules": "price"}
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                price_data = data["quoteSummary"]["result"][0]["price"]
                price = price_data.get("regularMarketPrice", {}).get("raw", 0)
                change_pct = price_data.get("regularMarketChangePercent", {}).get("raw", 0) * 100
                emoji = "🟢" if change_pct >= 0 else "🔴"
                results.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change_pct": change_pct,
                    "emoji": emoji
                })
        except Exception:
            pass
    return results


def format_us_stocks(stocks):
    """格式化美股数据"""
    if not stocks:
        return "暂无美股数据（可能为非交易日）\n"

    text = ""
    for s in stocks:
        sign = "+" if s["change_pct"] >= 0 else ""
        text += f"  {s['emoji']} {s['name']}({s['symbol']}): ${s['price']:,.2f} ({sign}{s['change_pct']:.2f}%)\n"
    return text


# ============== 加密货币模块 ==============
CRYPTO_IDS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "dogecoin", "cardano", "toncoin"]
CRYPTO_NAMES = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "toncoin": "TON",
}


def fetch_crypto():
    """通过CoinGecko获取加密货币数据"""
    results = []
    try:
        ids = ",".join(CRYPTO_IDS)
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true",
        }
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            for crypto_id in CRYPTO_IDS:
                if crypto_id in data:
                    info = data[crypto_id]
                    price = info.get("usd", 0)
                    change_24h = info.get("usd_24h_change", 0) or 0
                    market_cap = info.get("usd_market_cap", 0)
                    emoji = "🟢" if change_24h >= 0 else "🔴"
                    results.append({
                        "name": CRYPTO_NAMES.get(crypto_id, crypto_id),
                        "price": price,
                        "change_24h": change_24h,
                        "market_cap": market_cap,
                        "emoji": emoji
                    })
    except Exception as e:
        print(f"[Crypto Error] {e}")

    return results


def format_crypto(cryptos):
    """格式化加密货币数据"""
    if not cryptos:
        return "暂无加密货币数据\n"

    text = ""
    for c in cryptos:
        sign = "+" if c["change_24h"] >= 0 else ""
        if c["price"] >= 1:
            price_str = f"${c['price']:,.2f}"
        else:
            price_str = f"${c['price']:.4f}"

        # 市值格式化
        mc = c["market_cap"]
        if mc >= 1e12:
            mc_str = f"{mc/1e12:.2f}T"
        elif mc >= 1e9:
            mc_str = f"{mc/1e9:.2f}B"
        elif mc >= 1e6:
            mc_str = f"{mc/1e6:.2f}M"
        else:
            mc_str = f"{mc:,.0f}"

        text += f"  {c['emoji']} {c['name']}: {price_str} ({sign}{c['change_24h']:.2f}%) | 市值: ${mc_str}\n"
    return text


# ============== 恐惧贪婪指数 ==============
def fetch_fear_greed_index():
    """获取加密货币恐惧贪婪指数"""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            value = data["data"][0]["value"]
            classification = data["data"][0]["value_classification"]
            return {"value": value, "classification": classification}
    except Exception as e:
        print(f"[FGI Error] {e}")
    return None


# ============== 消息组装与发送 ==============
def build_morning_briefing():
    """组装早报内容"""
    now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
    date_str = now.strftime("%Y年%m月%d日 %A")

    # 抓取各模块数据
    print("[INFO] 正在抓取AI资讯...")
    ai_news = fetch_ai_news()

    print("[INFO] 正在抓取美股行情...")
    us_stocks = fetch_us_stocks()

    print("[INFO] 正在抓取加密货币数据...")
    cryptos = fetch_crypto()

    print("[INFO] 正在抓取恐惧贪婪指数...")
    fgi = fetch_fear_greed_index()

    # 组装消息
    msg = f"☀️ *每日早报 | {date_str}*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    # AI 资讯
    msg += "🤖 *AI 重要资讯*\n"
    msg += format_ai_news(ai_news)
    msg += "\n"

    # 美股行情
    msg += "📈 *美股行情*\n"
    msg += format_us_stocks(us_stocks)
    msg += "\n"

    # 加密货币
    msg += "₿ *加密货币行情 (24h)*\n"
    msg += format_crypto(cryptos)

    # 恐惧贪婪指数
    if fgi:
        value = int(fgi["value"])
        if value <= 25:
            fgi_emoji = "😱"
        elif value <= 45:
            fgi_emoji = "😰"
        elif value <= 55:
            fgi_emoji = "😐"
        elif value <= 75:
            fgi_emoji = "😊"
        else:
            fgi_emoji = "🤑"
        msg += f"\n  {fgi_emoji} 恐惧贪婪指数: {fgi['value']} ({fgi['classification']})\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🤖 由早报机器人自动生成"

    return msg


def send_telegram_message(text):
    """发送Telegram消息"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"[SUCCESS] 早报推送成功 - {datetime.now()}")
        else:
            print(f"[ERROR] 推送失败: {resp.status_code} - {resp.text}")
            # Markdown解析失败时，用纯文本重试
            payload["parse_mode"] = None
            requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"[ERROR] 发送失败: {e}")


def job():
    """定时任务"""
    print(f"\n[INFO] 开始生成早报 - {datetime.now()}")
    try:
        msg = build_morning_briefing()
        send_telegram_message(msg)
    except Exception as e:
        print(f"[ERROR] 早报生成失败: {e}")
        send_telegram_message(f"⚠️ 早报生成失败: {str(e)}")


# ============== 主程序 ==============
if __name__ == "__main__":
    print("=" * 50)
    print("📰 Telegram 每日早报机器人")
    print(f"⏰ 推送时间: 每天 {PUSH_TIME}")
    print(f"🆔 Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 50)

    # 启动时先发送一次测试
    import sys
    if "--test" in sys.argv:
        print("\n[TEST] 发送测试早报...")
        job()
        print("[TEST] 测试完成")
        sys.exit(0)

    # 设置定时任务
    schedule.every().day.at(PUSH_TIME).do(job)
    print(f"\n[INFO] 定时任务已设置，等待执行...")

    # 保持运行
    while True:
        schedule.run_pending()
        time.sleep(30)