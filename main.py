import os
import asyncio
import aiohttp
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

# 环境变量
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# 获取新闻
async def get_news():
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "country": "tw",
        "pageSize": 10,
        "apiKey": os.getenv("NEWS_API_KEY", "")
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                articles = data.get("articles", [])
                return articles
    except Exception as e:
        print(f"[ERROR] 获取新闻失败: {e}")
        return []

# 获取天气
async def get_weather():
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": "Taipei",
        "appid": os.getenv("WEATHER_API_KEY", ""),
        "units": "metric",
        "lang": "zh_tw"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                temp = data["main"]["temp"]
                desc = data["weather"][0]["description"]
                humidity = data["main"]["humidity"]
                return f"🌡️ 溫度：{temp}°C\n☁️ 天氣：{desc}\n💧 濕度：{humidity}%"
    except Exception as e:
        print(f"[ERROR] 获取天气失败: {e}")
        return "⚠️ 天氣資訊獲取失敗"

# 获取每日一句
async def get_daily_quote():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.quotable.io/random") as resp:
                data = await resp.json()
                return f"💬 {data['content']}\n— {data['author']}"
    except:
        return "💬 每一天都是新的開始！"

# 发送早报
async def send_morning_briefing():
    print(f"[INFO] 开始生成早报... {datetime.now()}")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # 获取数据
    news_list, weather, quote = await asyncio.gather(
        get_news(),
        get_weather(),
        get_daily_quote()
    )

    # 日期
    today = datetime.now().strftime("%Y年%m月%d日 %A")

    # 组装消息
    msg = f"☀️ **早安！今日早報**\n"
    msg += f"📅 {today}\n"
    msg += f"{'─' * 30}\n\n"

    # 天气
    msg += f"🌤 **台北天氣**\n{weather}\n\n"

    # 新闻
    msg += f"📰 **今日新聞 TOP 10**\n"
    if news_list:
        for i, article in enumerate(news_list, 1):
            title = article.get("title", "無標題")
            url = article.get("url", "")
            msg += f"{i}. [{title}]({url})\n"
    else:
        msg += "暫無新聞\n"

    msg += f"\n{'─' * 30}\n"
    msg += f"✨ **每日一句**\n{quote}\n"
    msg += f"\n祝你有美好的一天！🎉"

    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=msg,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        print("[INFO] 早报发送成功！")
    except Exception as e:
        print(f"[ERROR] 发送失败: {e}")

# 主函数
async def main():
    print("=" * 40)
    print("📰 每日早報機器人 (Railway)")
    print("⏰ 推送時間: 08:00 (UTC+8)")
    print("=" * 40)

    # 启动时先发一次
    await send_morning_briefing()

    # 定时任务
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(send_morning_briefing, "cron", hour=8, minute=0)
    scheduler.start()
    print("[INFO] 定时任务已设置，每天08:00推送")

    # 保持运行
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)
    main_loop.run_until_complete(main())