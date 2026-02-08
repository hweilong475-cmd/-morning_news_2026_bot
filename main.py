import os
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== 環境變量 ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==================== 對話歷史 ====================
conversation_history = []
MAX_HISTORY = 20

# ==================== RSS 新聞來源 ====================
RSS_SOURCES = {
    "🌍 BBC 中文": "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml",
    "🌏 路透社": "https://feeds.reuters.com/reuters/topNews",
    "🇺🇸 CNN": "http://rss.cnn.com/rss/edition.rss",
    "💻 TechCrunch": "https://techcrunch.com/feed/",
    "📱 The Verge": "https://www.theverge.com/rss/index.xml",
    "🤖 AI News": "https://www.artificialintelligence-news.com/feed/",
    "🔬 Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "💡 Wired": "https://www.wired.com/feed/rss",
    "🏢 TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "📰 紐約時報科技": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
}

# ==================== 抓取 RSS ====================
async def fetch_rss(session, source_name, url, max_items=5):
    articles = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            root = ET.fromstring(text)

            # 標準 RSS 2.0
            items = root.findall(".//item")
            # Atom 格式
            if not items:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//atom:entry", ns)

            count = 0
            for item in items:
                if count >= max_items:
                    break

                # RSS 2.0
                title = item.findtext("title")
                link = item.findtext("link")

                # Atom
                if not title:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    title = item.findtext("atom:title", namespaces=ns)
                if not link:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    link_elem = item.find("atom:link", namespaces=ns)
                    if link_elem is not None:
                        link = link_elem.get("href", "")

                if title and title.strip():
                    articles.append({
                        "title": title.strip(),
                        "url": link.strip() if link else "",
                        "source": source_name
                    })
                    count += 1
    except Exception as e:
        print(f"[ERROR] RSS抓取失敗 {source_name}: {e}")
    return articles

# ==================== 抓取所有新聞 ====================
async def fetch_all_news():
    all_news = {}
    async with aiohttp.ClientSession() as session:
        tasks = []
        for name, url in RSS_SOURCES.items():
            tasks.append(fetch_rss(session, name, url, max_items=5))

        results = await asyncio.gather(*tasks)

        for name, articles in zip(RSS_SOURCES.keys(), results):
            if articles:
                all_news[name] = articles
    return all_news

# ==================== 用 Gemini 總結新聞 ====================
async def summarize_with_gemini(news_text):
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""你是一位專業的新聞編輯。請根據以下新聞標題，用繁體中文寫一段「今日重點摘要」，200字以內，突出最重要的3-5條新聞：

{news_text}

要求：
1. 繁體中文
2. 簡潔有力
3. 突出重點
4. 分點列出"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[ERROR] Gemini總結失敗: {e}")
        return None

# ==================== Gemini 對話 ====================
async def chat_with_gemini(user_message):
    global conversation_history

    if not GEMINI_API_KEY:
        return "❌ 未設置 GEMINI_API_KEY"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    # 構建對話歷史
    conversation_history.append({"role": "user", "parts": [{"text": user_message}]})

    # 限制歷史長度
    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]

    system_instruction = """你是一個智能助手，運行在 Telegram 機器人中。
你的特點：
1. 使用繁體中文回答
2. 回答簡潔清晰
3. 擅長分析新聞、科技、AI相關話題
4. 友善且專業
5. 如果用戶問新聞相關問題，盡量提供有價值的分析"""

    payload = {
        "contents": conversation_history,
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2000
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                reply = data["candidates"][0]["content"]["parts"][0]["text"]

                # 保存AI回覆到歷史
                conversation_history.append({"role": "model", "parts": [{"text": reply}]})

                return reply
    except Exception as e:
        print(f"[ERROR] Gemini對話失敗: {e}")
        # 移除失敗的消息
        conversation_history.pop()
        return f"❌ AI回覆失敗：{str(e)}"

# ==================== 格式化新聞 ====================
def format_news_section(articles):
    text = ""
    for i, article in enumerate(articles, 1):
        title = article["title"]
        url = article.get("url", "")
        if url:
            text += f"  {i}. [{title}]({url})\n"
        else:
            text += f"  {i}. {title}\n"
    return text

# ==================== 分段發送 ====================
def split_message(text, max_len=4000):
    parts = []
    lines = text.split("\n")
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)
    return parts

# ==================== 生成並發送早報 ====================
async def generate_and_send_briefing(bot=None):
    print(f"[INFO] 開始生成早報... {datetime.now()}")

    if not bot:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)

    all_news = await fetch_all_news()

    if not all_news:
        await bot.send_message(chat_id=CHAT_ID, text="⚠️ 今日新聞抓取失敗，請稍後重試")
        return

    today = datetime.now().strftime("%Y年%m月%d日")

    # 組裝消息
    msg = f"☀️ *每日情報早報*\n"
    msg += f"📅 {today}\n"
    msg += f"{'━' * 28}\n\n"

    # 收集所有標題用於AI總結
    all_titles = []

    # 分類整理
    categories = {
        "🌍 全球要聞": ["🌍 BBC 中文", "🌏 路透社", "🇺🇸 CNN"],
        "💻 科技產業": ["💻 TechCrunch", "📱 The Verge", "🔬 Ars Technica", "💡 Wired", "📰 紐約時報科技"],
        "🤖 AI 動態": ["🤖 AI News", "🏢 TechCrunch AI"]
    }

    for cat_name, sources in categories.items():
        cat_articles = []
        for source in sources:
            if source in all_news:
                cat_articles.extend(all_news[source])

        if cat_articles:
            msg += f"*{cat_name}*\n"
            # 去重
            seen = set()
            unique = []
            for a in cat_articles:
                if a["title"] not in seen:
                    seen.add(a["title"])
                    unique.append(a)
                    all_titles.append(a["title"])
            msg += format_news_section(unique[:8])
            msg += "\n"

    # AI 總結
    if all_titles:
        titles_text = "\n".join(all_titles[:20])
        summary = await summarize_with_gemini(titles_text)
        if summary:
            msg += f"{'━' * 28}\n"
            msg += f"📝 *AI 今日重點摘要*\n\n"
            msg += f"{summary}\n\n"

    msg += f"{'━' * 28}\n"
    msg += f"💬 直接發消息可與 AI 對話\n"
    msg += f"📌 /news 手動獲取最新新聞\n"
    msg += f"🕗 每日 08:00 自動推送"

    # 發送
    try:
        if len(msg) > 4000:
            parts = split_message(msg)
            for part in parts:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=part,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                await asyncio.sleep(1)
        else:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        print("[INFO] ✅ 早報發送成功！")
    except Exception as e:
        print(f"[ERROR] Markdown發送失敗: {e}")
        try:
            clean = msg.replace("*", "").replace("[", "").replace("]", "").replace("(", " ").replace(")", "")
            parts = split_message(clean)
            for part in parts:
                await bot.send_message(chat_id=CHAT_ID, text=part, disable_web_page_preview=True)
                await asyncio.sleep(1)
        except Exception as e2:
            print(f"[ERROR] 純文字也失敗: {e2}")

# ==================== 指令處理 ====================

# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if CHAT_ID and user_id != CHAT_ID:
        await update.message.reply_text("⛔ 你沒有權限使用此機器人")
        return

    welcome = (
        "👋 *歡迎使用情報早報機器人！*\n\n"
        "📰 *功能一覽：*\n"
        "• 每日 08:00 自動推送新聞早報\n"
        "• 直接發消息與 AI 對話\n"
        "• AI 可以幫你分析新聞、回答問題\n\n"
        "📌 *指令列表：*\n"
        "/news - 立即獲取最新新聞\n"
        "/ai - AI 新聞分析\n"
        "/clear - 清除對話歷史\n"
        "/help - 查看幫助\n\n"
        "💬 直接打字就能跟 AI 聊天！"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

# /news
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if CHAT_ID and user_id != CHAT_ID:
        return

    await update.message.reply_text("📡 正在抓取最新新聞，請稍候...")
    await generate_and_send_briefing(context.bot)

# /ai - AI分析當前新聞
async def cmd_ai_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if CHAT_ID and user_id != CHAT_ID:
        return

    await update.message.reply_text("🤖 正在分析今日新聞...")

    all_news = await fetch_all_news()
    all_titles = []
    for source, articles in all_news.items():
        for a in articles:
            all_titles.append(f"[{source}] {a['title']}")

    if not all_titles:
        await update.message.reply_text("⚠️ 無法獲取新聞")
        return

    prompt = f"""以下是今天的新聞標題，請用繁體中文做深度分析：

{chr(10).join(all_titles[:25])}

請分析：
1. 今天最重要的3件事是什麼？為什麼重要？
2. AI/科技領域有什麼值得關注的動態？
3. 這些新聞之間有什麼關聯？
4. 對普通人有什麼影響？"""

    reply = await chat_with_gemini(prompt)
    await update.message.reply_text(f"🤖 *AI 新聞深度分析*\n\n{reply}", parse_mode="Markdown")

# /clear
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if CHAT_ID and user_id != CHAT_ID:
        return

    global conversation_history
    conversation_history = []
    await update.message.reply_text("🗑️ 對話歷史已清除！")

# /help
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *使用說明*\n\n"
        "🔹 /start - 開始使用\n"
        "🔹 /news - 立即獲取最新新聞\n"
        "🔹 /ai - AI 深度分析今日新聞\n"
        "🔹 /clear - 清除對話歷史\n"
        "🔹 /help - 查看此幫助\n\n"
        "💬 *AI 對話：*\n"
        "直接發送任何消息即可與 AI 對話\n"
        "AI 擅長分析新聞、科技、AI 相關話題\n\n"
        "📰 *新聞來源：*\n"
        "BBC中文 | 路透社 | CNN\n"
        "TechCrunch | The Verge | Ars Technica\n"
        "Wired | 紐約時報 | AI News\n\n"
        "⏰ 每日 08:00 自動推送早報"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# 普通消息 → AI對話
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if CHAT_ID and user_id != CHAT_ID:
        return

    user_text = update.message.text
    if not user_text:
        return

    # 顯示正在輸入
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    reply = await chat_with_gemini(user_text)

    # Telegram 消息限制 4096 字
    if len(reply) > 4000:
        parts = split_message(reply)
        for part in parts:
            await update.message.reply_text(part)
            await asyncio.sleep(0.5)
    else:
        await update.message.reply_text(reply)

# ==================== 定時推送 ====================
async def scheduled_briefing(app):
    await generate_and_send_briefing(app.bot)

# ==================== 主函數 ====================
def main():
    print("=" * 45)
    print("📰 情報早報 + AI 對話機器人")
    print("📋 全球新聞 | 科技 | AI | Gemini 對話")
    print("📡 新聞來源：BBC | 路透社 | CNN | TechCrunch...")
    print("⏰ 每日 08:00 自動推送")
    print("=" * 45)

    # 建立 Application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 註冊指令
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("ai", cmd_ai_analysis))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("help", cmd_help))

    # 普通消息 → AI對話
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 定時任務
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(scheduled_briefing, "cron", hour=8, minute=0, args=[app])
    scheduler.start()
    print("[INFO] ✅ 定時任務已啟動，每天 08:00 推送")

    # 啟動機器人
    print("[INFO] ✅ 機器人啟動中...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()