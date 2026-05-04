# ----- FAST HUMAN FRIENDLY CHATBOT -----

import httpx
import random
import urllib.parse
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ChatType

from Nia.database import chatbot_collection
   
# -------- SETTINGS --------

API_URL = "https://gpt33-8dbb8bea9d02."

MAX_HISTORY = 6

FALLBACK_RESPONSES = [
    "acha sahi 🙂",
    "haan yaar",
    "lol 😅",
    "samjha",
    "acha fir",
]


# -------- HUMAN STYLE PROMPT --------

SYSTEM_PROMPT = """
You are a chill Indian friend chatting on WhatsApp.

Style:
- Hinglish me baat kar
- Short replies (mostly 1 line)
- Natural aur thoda imperfect (like real human)
- Kabhi kabhi emoji use kar 🙂😅
- Har reply me emoji zaroori nahi

Behavior:
- Over-explain mat kar
- Simple aur casual reh
- Thoda mood dikh (happy, bored, fun)
- Kabhi kabhi slang use kar (yaar, bhai, arey, lol)

Examples:

User: kaisa hai
Bot: badhiya hu bhai 🙂 tu bol

User: kya kar raha
Bot: kuch khaas nahi yaar

User: bore ho raha
Bot: same yaar 😅 kuch karte hai

User: khaana khaya
Bot: haan abhi khaya 🙂 tu?
"""


# -------- SPEED OPTIMIZATION --------

http_client = httpx.AsyncClient(timeout=5)
AI_CACHE = {}


# -------- AI CORE --------

async def get_ai_reply(chat_id, user_text):

    if user_text in AI_CACHE:
        return AI_CACHE[user_text]

    doc = chatbot_collection.find_one({"chat_id": chat_id}) or {}
    history = doc.get("history", [])

    prompt = SYSTEM_PROMPT + "\nUser: " + user_text + "\nBot:"
    encoded = urllib.parse.quote(prompt)
    url = f"{API_URL}{encoded}"

    try:
        resp = await http_client.get(url)

        if resp.status_code != 200:
            return random.choice(FALLBACK_RESPONSES)

        data = resp.json()

        if "reply" in data:
            reply = data["reply"]

        elif "response" in data:
            reply = data["response"]

        elif "answer" in data:
            reply = data["answer"]

        elif "message" in data:
            reply = data["message"]

        else:
            reply = str(data)

    except:
        return random.choice(FALLBACK_RESPONSES)

    reply = reply.strip()

    AI_CACHE[user_text] = reply

    new_history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": reply}
    ]

    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-MAX_HISTORY * 2:]

    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"history": new_history}},
        upsert=True
    )

    return reply


# -------- MESSAGE HANDLER --------

async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    if not msg or not msg.text:
        return

    # ❌ bot to bot ignore
    if msg.from_user and msg.from_user.is_bot:
        return

    text = msg.text.strip()

    if text.startswith("/"):
        return

    chat = update.effective_chat
    should_reply = False

    # ---- PRIVATE ----
    if chat.type == ChatType.PRIVATE:
        should_reply = True

    # ---- GROUP ----
    elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:

        bot_username = (context.bot.username or "").lower()

        if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
            should_reply = True

        elif f"@{bot_username}" in text.lower():
            should_reply = True
            text = text.replace(f"@{bot_username}", "").strip()

        elif text.lower().startswith(("hi", "hey", "hello", "nia", "oye", "sun")):
            should_reply = True

    if not should_reply:
        return

    await context.bot.send_chat_action(chat.id, ChatAction.TYPING)

    reply = await get_ai_reply(chat.id, text)

    # ✅ directly reply (no stylize)
    await msg.reply_text(reply)


# -------- ECONOMY SUPPORT --------

async def ask_mistral_raw(system_prompt, user_input, max_tokens=150):

    prompt = system_prompt + "\nUser: " + user_input + "\nBot:"
    encoded = urllib.parse.quote(prompt)
    url = f"{API_URL}{encoded}"

    try:
        resp = await http_client.get(url)

        if resp.status_code != 200:
            return None

        data = resp.json()

        if "reply" in data:
            return data["reply"]

        elif "response" in data:
            return data["response"]

        elif "answer" in data:
            return data["answer"]

        elif "message" in data:
            return data["message"]

        else:
            return str(data)

    except:
        return None


# -------- COMMANDS --------

async def chatbot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🤖 AI Chatbot Active\n\n"
        "Mujhse normal chat karo 🙂"
    )


async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text("Use: /ask kya kar raha")
        return

    text = " ".join(context.args)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    reply = await get_ai_reply(update.effective_chat.id, text)

    # ✅ no stylize here too
    await update.message.reply_text(reply)
