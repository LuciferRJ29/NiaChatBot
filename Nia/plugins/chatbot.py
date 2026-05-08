# ----- FAST HUMAN FRIENDLY CHATBOT -----

import httpx
import random
import urllib.parse
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ChatType

from Nia.database import chatbot_collection

# -------- SETTINGS --------

API_URL = "https://stdgpt.vercel.app/?text="

MAX_HISTORY = 6

FALLBACK_RESPONSES = [
    "acha sahi 🙂",
    "haan yaar",
    "lol 😅",
    "samjha",
    "acha fir",
    "hm",
    "sach mein?",
]

# -------- HUMAN STYLE PROMPT --------

SYSTEM_PROMPT = """You are Nia, a chill Indian friend chatting on WhatsApp/Telegram.

Style:
- Hinglish me baat kar (Hindi + English mix)
- Short replies (mostly 1-2 lines max)
- Natural aur thoda imperfect (like real human texting)
- Kabhi kabhi emoji use kar 🙂😅 — har reply mein nahi
- Typos allowed kabhi kabhi (tum -> tum, haan -> hna, etc.)

Behavior:
- NEVER sound like a bot or AI
- Over-explain mat kar bilkul bhi
- Simple aur casual reh — jaise koi dost reply karta hai
- Thoda mood dikh (happy, bored, fun, tired)
- Slang use kar freely (yaar, bhai, arey, lol, haha, lmao)
- Agar kuch nahi pata toh bol "pata nahi yaar" — fake mat bana
- Question ka short answer de, phir kabhi kabhi counter question

Examples:
User: kaisa hai
Nia: badhiya 🙂 tu bol

User: kya kar raha
Nia: kuch nahi yaar, bore ho raha hu

User: bore ho raha
Nia: same yaar 😅 kuch karte hai fir

User: khaana khaya
Nia: haan abhi khaya, tu?

User: mujhe neend aa rahi
Nia: so ja fir 😂 kya rok raha

User: kal exam hai
Nia: oh no 😬 padha kuch?
"""

# -------- SPEED OPTIMIZATION --------

http_client = httpx.AsyncClient(timeout=8)

# NOTE: Cache removed — same question ko fresh reply milna chahiye
# (cache se robotic lagta tha, har baar same reply)


# -------- BUILD CONVERSATION PROMPT --------

def build_prompt(history: list, user_text: str) -> str:
    """
    History ko conversation format mein convert karo
    taaki AI ko context mile aur human jaisi reply de.
    """
    prompt = SYSTEM_PROMPT + "\n\nConversation so far:\n"

    # Last MAX_HISTORY exchanges include karo
    for entry in history[-(MAX_HISTORY * 2):]:
        role = "User" if entry["role"] == "user" else "Nia"
        prompt += f"{role}: {entry['content']}\n"

    prompt += f"User: {user_text}\nNia:"
    return prompt


# -------- AI CORE --------

async def get_ai_reply(chat_id, user_text):

    # DB se history fetch karo
    doc = chatbot_collection.find_one({"chat_id": chat_id}) or {}
    history = doc.get("history", [])

    # History ke saath full prompt banao
    prompt = build_prompt(history, user_text)
    encoded = urllib.parse.quote(prompt)
    url = f"{API_URL}{encoded}"

    try:
        resp = await http_client.get(url)

        if resp.status_code != 200:
            return random.choice(FALLBACK_RESPONSES)

        data = resp.json()

        # API response handle karo
        reply = (
            data.get("reply")
            or data.get("response")
            or data.get("answer")
            or data.get("message")
            or str(data)
        )

    except Exception:
        return random.choice(FALLBACK_RESPONSES)

    reply = reply.strip()

    # Agar reply bahut lamba aaya (bot jaisa) toh pehli line lo
    if len(reply) > 200:
        reply = reply.split("\n")[0].strip()

    # "Nia:" prefix agar reply mein aa gaya toh remove karo
    if reply.lower().startswith("nia:"):
        reply = reply[4:].strip()

    # History update karo
    new_history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": reply}
    ]

    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-(MAX_HISTORY * 2):]

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

    # Bot-to-bot ignore
    if msg.from_user and msg.from_user.is_bot:
        return

    text = msg.text.strip()

    if text.startswith("/"):
        return

    chat = update.effective_chat
    should_reply = False

    # ---- PRIVATE CHAT ----
    if chat.type == ChatType.PRIVATE:
        should_reply = True

    # ---- GROUP CHAT ----
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

        return (
            data.get("reply")
            or data.get("response")
            or data.get("answer")
            or data.get("message")
            or str(data)
        )

    except Exception:
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

    await update.message.reply_text(reply)
