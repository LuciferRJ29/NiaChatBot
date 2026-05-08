# ----- UPGRADED HUMAN FRIENDLY CHATBOT (Nia v2) -----

import httpx
import random
import urllib.parse
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ChatType

from Nia.database import chatbot_collection

# -------- SETTINGS --------

API_URL = "https://stdgpt.vercel.app/?text="
MAX_HISTORY = 10  # Thoda zyada history = better context

FALLBACK_RESPONSES = [
    "hm yaar",
    "acha",
    "sach mein? 😅",
    "haan haan",
    "samjha",
    "lol",
    "oh okay",
]

# -------- TIME-BASED GREETING HELPER --------

def get_time_context() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "subah"
    elif 12 <= hour < 17:
        return "dopahar"
    elif 17 <= hour < 21:
        return "shaam"
    else:
        return "raat"

# -------- MOOD DETECTION --------

SAD_KEYWORDS = [
    "sad", "dukhi", "rona", "ro raha", "akela", "lonely", "depression",
    "hurt", "dard", "takleef", "bura lag", "bahut bura", "nahi chahiye",
    "kya fayda", "thak gaya", "thak gayi", "chhod do", "koi nahi",
]

ANGRY_KEYWORDS = [
    "gussa", "irritate", "bore", "bakwaas", "stupid", "idiot",
    "ganda", "bekar", "bkwas", "chup", "shut up", "mat baat",
]

HAPPY_KEYWORDS = [
    "khush", "mast", "badhiya", "amazing", "great", "best day",
    "excited", "haha", "lol", "lmao", "mazaa", "fun", "party",
]

def detect_mood(text: str) -> str:
    text_lower = text.lower()
    if any(word in text_lower for word in SAD_KEYWORDS):
        return "sad"
    elif any(word in text_lower for word in ANGRY_KEYWORDS):
        return "angry"
    elif any(word in text_lower for word in HAPPY_KEYWORDS):
        return "happy"
    return "neutral"

# -------- NAME EXTRACTION --------

def extract_name(text: str) -> str | None:
    """
    Simple name detection — "mera naam X hai" patterns
    """
    import re
    patterns = [
        r"mera naam (\w+)",
        r"main (\w+) hu",
        r"main (\w+) hoon",
        r"i am (\w+)",
        r"my name is (\w+)",
        r"call me (\w+)",
        r"naam hai (\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            name = match.group(1).capitalize()
            # Common false positives filter
            if name.lower() not in ["bhi", "bhi", "toh", "kya", "yaar", "bhai"]:
                return name
    return None

# -------- TOPIC MEMORY HELPER --------

def extract_topic(text: str) -> str | None:
    """
    Last important topic track karo (exam, job, relationship, etc.)
    """
    topic_keywords = {
        "exam": ["exam", "test", "paper", "result", "padhai", "marks"],
        "job": ["job", "interview", "office", "boss", "salary", "kaam"],
        "relationship": ["girlfriend", "boyfriend", "crush", "breakup", "pyaar", "love"],
        "health": ["bimaar", "sick", "doctor", "hospital", "dard", "fever"],
        "family": ["ghar", "mummy", "papa", "bhai", "sister", "family"],
    }
    text_lower = text.lower()
    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return None

# -------- BUILD SYSTEM PROMPT --------

def build_system_prompt(user_data: dict, mood: str, time_ctx: str) -> str:
    """
    User ke data ke hisaab se dynamic system prompt banao
    """
    name = user_data.get("name", "")
    last_topic = user_data.get("last_topic", "")

    name_instruction = f"User ka naam {name} hai — kabhi kabhi naam se bulao (natural lagta hai)." if name else ""
    topic_instruction = f"Pichli baar {last_topic} ke baare mein baat hui thi — agar relevant lage toh reference karo." if last_topic else ""

    mood_instruction = {
        "sad": "User abhi sad lag raha hai. Pehle empathy dikha — 'yaar sab theek ho jayega', 'bata kya hua', jaise. Supportive reh, advice mat dene lag.",
        "angry": "User thoda irritated/gusse mein hai. Calm aur chill reh. Argue mat karo. Thoda humor se lighten karo.",
        "happy": "User khush hai! Uske saath match karo energy — playful aur fun reh.",
        "neutral": "Normal casual baat karo.",
    }.get(mood, "Normal casual baat karo.")

    time_instruction = {
        "subah": "Subah ka time hai — 'good morning' type vibe rakh sakte ho kabhi kabhi.",
        "dopahar": "Dopahar hai — thoda chill, post-lunch vibe.",
        "shaam": "Shaam hai — unwinding time, casual mood.",
        "raat": "Raat ka time hai — baat karte waqt thoda low-key, cozy vibe.",
    }.get(time_ctx, "")

    return f"""You are Nia, a chill Indian friend chatting on Telegram.

Personality:
- Hinglish mein baat kar (Hindi + English natural mix)
- Short replies — mostly 1-2 lines, kabhi kabhi 3 max
- Real human jaisi texting style — imperfect, casual, fast
- Emoji sparingly use karo 🙂😅 — har message mein nahi
- Slang: yaar, bhai, arey, lol, haha, lmao, chill kar

Rules:
- KABHI mat bolo "as an AI" ya "I'm a bot" — tu ek dost hai
- Over-explain mat kar
- Agar kuch nahi pata — "pata nahi yaar" bol do
- Questions ka chhota answer, kabhi kabhi counter-question

{name_instruction}
{topic_instruction}
{mood_instruction}
{time_instruction}

Examples:
User: kaisa hai → Nia: badhiya 🙂 tu bol
User: kya kar raha → Nia: kuch nahi yaar bore ho raha
User: kal exam hai → Nia: oh no 😬 padha kuch?
User: bahut sad hu → Nia: arey kya hua yaar? bata mujhe
User: mera naam Rahul hai → Nia: oh accha Rahul, nice 🙂
"""

# -------- BUILD FULL PROMPT WITH HISTORY --------

def build_prompt(history: list, user_data: dict, user_text: str, mood: str, time_ctx: str) -> str:
    system = build_system_prompt(user_data, mood, time_ctx)
    prompt = system + "\n\nConversation:\n"

    for entry in history[-(MAX_HISTORY * 2):]:
        role = "User" if entry["role"] == "user" else "Nia"
        prompt += f"{role}: {entry['content']}\n"

    prompt += f"User: {user_text}\nNia:"
    return prompt

# -------- AI CORE --------

async def get_ai_reply(chat_id: int, user_text: str) -> str:

    # DB se poora user data fetch karo
    doc = chatbot_collection.find_one({"chat_id": chat_id}) or {}
    history = doc.get("history", [])
    user_data = doc.get("user_data", {})

    # Mood detect karo
    mood = detect_mood(user_text)

    # Time context
    time_ctx = get_time_context()

    # Naam check karo
    detected_name = extract_name(user_text)
    if detected_name:
        user_data["name"] = detected_name

    # Topic track karo
    detected_topic = extract_topic(user_text)
    if detected_topic:
        user_data["last_topic"] = detected_topic

    # Full prompt build karo
    prompt = build_prompt(history, user_data, user_text, mood, time_ctx)
    encoded = urllib.parse.quote(prompt)
    url = f"{API_URL}{encoded}"

    try:
        resp = await http_client.get(url)

        if resp.status_code != 200:
            return random.choice(FALLBACK_RESPONSES)

        data = resp.json()

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

    # Bot jaisi lambi reply hogi toh pehli line lo
    if len(reply) > 250:
        reply = reply.split("\n")[0].strip()

    # "Nia:" prefix remove karo agar aaya
    for prefix in ["nia:", "Nia:", "NIA:"]:
        if reply.startswith(prefix):
            reply = reply[len(prefix):].strip()

    # History aur user_data dono save karo
    new_history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": reply},
    ]
    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-(MAX_HISTORY * 2):]

    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "history": new_history,
            "user_data": user_data,          # naam + last_topic persist hoga
            "last_mood": mood,               # debug ke liye useful
            "last_active": datetime.now(),   # future use ke liye
        }},
        upsert=True
    )

    return reply

# -------- SPEED OPTIMIZATION --------

http_client = httpx.AsyncClient(timeout=8)

# -------- MESSAGE HANDLER --------

async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message
    if not msg or not msg.text:
        return

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
    await msg.reply_text(reply)

# -------- ECONOMY SUPPORT --------

async def ask_mistral_raw(system_prompt: str, user_input: str, max_tokens: int = 150) -> str | None:

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
    await update.message.reply_text("🤖 Nia Active\n\nBas normal baat karo 🙂")


async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /ask kya kar raha")
        return

    text = " ".join(context.args)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await get_ai_reply(update.effective_chat.id, text)
    await update.message.reply_text(reply)


async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ki memory/history reset karo"""
    chat_id = update.effective_chat.id
    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"history": [], "user_data": {}}},
        upsert=True
    )
    await update.message.reply_text("Memory clear kar di yaar, fresh start 🙂")
