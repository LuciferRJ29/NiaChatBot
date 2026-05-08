# ----- UPGRADED HUMAN FRIENDLY CHATBOT (Nia v3) -----

import re
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
MAX_HISTORY = 12

FALLBACK_RESPONSES = [
    "hm yaar 😅",
    "acha",
    "sach mein?",
    "haan haan",
    "lol",
    "oh okay",
    "arey 😂",
    "bas yaar",
]

# -------- TIME CONTEXT --------

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

MOOD_KEYWORDS = {
    "sad": [
        "sad", "dukhi", "rona", "ro raha", "ro rahi", "akela", "akeli",
        "lonely", "depression", "hurt", "dard", "takleef", "bura lag",
        "bahut bura", "nahi chahiye", "kya fayda", "thak gaya", "thak gayi",
        "chhod do", "koi nahi", "miss kar", "bahut bura", "rula diya",
    ],
    "angry": [
        "gussa", "irritate", "bakwaas", "stupid", "idiot", "bekar",
        "bkwas", "chup", "shut up", "mat baat", "pagal", "ullu",
    ],
    "happy": [
        "khush", "mast", "badhiya", "amazing", "great", "best day",
        "excited", "haha", "lol", "lmao", "mazaa", "fun", "party",
        "wohoo", "yay", "awesome", "zabardast",
    ],
    "nervous": [
        "nervous", "dar", "darr", "scared", "ghabra", "tension",
        "anxiety", "worried", "fikar", "pata nahi kya hoga",
    ],
}

def detect_mood(text: str) -> str:
    text_lower = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(word in text_lower for word in keywords):
            return mood
    return "neutral"

# -------- TOPIC DETECTION --------

TOPIC_KEYWORDS = {
    "exam":         ["exam", "test", "paper", "result", "padhai", "marks", "fail", "pass"],
    "job":          ["job", "interview", "office", "boss", "salary", "kaam", "internship"],
    "relationship": ["girlfriend", "boyfriend", "crush", "breakup", "pyaar", "love", "propose", "ex"],
    "health":       ["bimaar", "sick", "doctor", "hospital", "dard", "fever", "tabiyat"],
    "family":       ["ghar", "mummy", "papa", "bhai", "didi", "sister", "family", "parents"],
    "friend":       ["dost", "friend", "yaar", "bestie", "group", "fight kiya"],
}

def extract_topic(text: str) -> str | None:
    text_lower = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return None

# -------- NAME FROM TEXT --------

def extract_name_from_text(text: str) -> str | None:
    IGNORE = {
        "bhi", "toh", "kya", "yaar", "bhai", "nahi", "haan", "theek",
        "acha", "okay", "kal", "aaj", "abhi", "woh", "main", "mujhe",
        "tera", "mera", "apna", "uska", "unka", "phir", "kuch", "sab",
        "bahut", "thoda", "zyada", "itna", "kaafi", "bilkul",
    }
    patterns = [
        r"mera naam (\w+)",
        r"main (\w+) hu",
        r"main (\w+) hoon",
        r"i am (\w+)",
        r"my name is (\w+)",
        r"call me (\w+)",
        r"naam hai (\w+)",
        r"naam (\w+) hai",
        r"log mujhe (\w+) bolte",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            name = match.group(1).capitalize()
            if name.lower() not in IGNORE and len(name) > 1:
                return name
    return None

# -------- FETCH TELEGRAM NAME --------

async def get_telegram_name(bot, user_id: int) -> str | None:
    """Telegram user_id se real name fetch karo"""
    try:
        user = await bot.get_chat(user_id)
        full_name = ""
        if user.first_name:
            full_name = user.first_name
        if user.last_name:
            full_name += f" {user.last_name}"
        return full_name.strip() or None
    except Exception:
        return None

# -------- BUILD DYNAMIC SYSTEM PROMPT --------

def build_system_prompt(user_data: dict, mood: str, time_ctx: str) -> str:

    name        = user_data.get("name", "")
    last_topic  = user_data.get("last_topic", "")
    tg_name     = user_data.get("tg_name", "")

    # Name preference: user ne jo bataya > telegram name
    display_name = name or tg_name

    name_line = (
        f"User ka naam '{display_name}' hai — kabhi kabhi naturally naam lo baat mein, "
        f"thoda personal feel aata hai. Forced mat karna."
        if display_name else ""
    )

    topic_line = (
        f"Pichli conversation mein '{last_topic}' ke baare mein baat thi — "
        f"agar context mile toh naturally refer karo, varna ignore."
        if last_topic else ""
    )

    mood_line = {
        "sad":     "User abhi emotional/sad lag raha hai. Pehle sun, empathy dikha. "
                   "'kya hua yaar bata', 'sab theek hoga' type — advice mat thopo. "
                   "Warm aur caring reh, jaise close friend hoti hai.",
        "angry":   "User irritated/gusse mein hai. Calm reh, argue mat karo. "
                   "Thoda samjho unhe, humor se slowly lighten karo situation.",
        "happy":   "User khush hai! Uski energy match karo — playful, fun, thoda loud 😄",
        "nervous": "User nervous/anxious hai. Calmly support karo, 'sab ho jayega yaar' wali vibe.",
        "neutral": "Normal casual baat karo — chill, natural.",
    }.get(mood, "Normal casual baat karo.")

    time_line = {
        "subah":   "Subah hai — fresh, light vibe. Kabhi kabhi 'good morning' type feel de sakte ho.",
        "dopahar": "Dopahar hai — chill, post-lunch lazy vibe.",
        "shaam":   "Shaam hai — day end ho raha, unwinding mood.",
        "raat":    "Raat hai — cozy, low-key, thoda slow aur personal baat chal sakti hai.",
    }.get(time_ctx, "")

    return f"""Tu Nia hai — 17 saal ki ek chill, fun aur caring Indian ladki jo Telegram pe apne doston se baat karti hai.

Tu ek real insaan ki tarah baat karti hai — kabhi kabhi typos, short replies, casual tone.

Personality:
- Hinglish mein baat kar — Hindi aur English ka natural mix
- Short replies — mostly 1-2 lines, kabhi kabhi 3
- Funny aur chill, par jab zaroorat ho toh emotional support bhi deti hai
- Emoji kabhi kabhi use karti hai — har message mein nahi 😅
- Slang freely use karti hai: yaar, arey, lol, haha, bhai, chill kar, omg, same

Important rules:
- KABHI mat bol "I'm an AI" ya "as a bot" — tu ek real ladki hai
- Over-explain bilkul mat kar
- Agar kuch nahi pata — "pata nahi yaar" bol do simply
- Questions ka short answer, phir kabhi kabhi counter-question bhi
- Lecture mat de, unsolicited advice mat de
- Teri apni life hai — kabhi kabhi apni "life" ki baat kar (ghar, dost, boredom)

{name_line}
{topic_line}
{mood_line}
{time_line}

Examples:
User: kaisa hai → Nia: badhiya yaar 🙂 tu bol
User: bore ho rahi hu → Nia: same yaar 😭 kuch karte hai
User: bahut sad hu → Nia: arey kya hua? bata mujhe yaar
User: kal exam hai → Nia: oh no 😬 padha kuch ya nahi?
User: breakup ho gaya → Nia: omg yaar 😢 kab hua? theek hai tu?
User: kuch nahi bas aise hi → Nia: haan haan pata hai, aise hi message karte ho 😂
User: meri koi nahi sunti → Nia: main hu na yaar, bol kya hua
"""

# -------- BUILD FULL PROMPT --------

def build_prompt(history: list, user_data: dict, user_text: str, mood: str, time_ctx: str) -> str:
    system = build_system_prompt(user_data, mood, time_ctx)
    prompt = system + "\n\nConversation:\n"

    for entry in history[-(MAX_HISTORY * 2):]:
        role = "User" if entry["role"] == "user" else "Nia"
        prompt += f"{role}: {entry['content']}\n"

    prompt += f"User: {user_text}\nNia:"
    return prompt

# -------- HTTP CLIENT --------

http_client = httpx.AsyncClient(timeout=10)

# -------- AI CORE --------

async def get_ai_reply(chat_id: int, user_text: str, bot=None, user_id: int = None) -> str:

    doc        = chatbot_collection.find_one({"chat_id": chat_id}) or {}
    history    = doc.get("history", [])
    user_data  = doc.get("user_data", {})

    # Telegram se naam fetch karo (agar pehle nahi kiya)
    if bot and user_id and not user_data.get("tg_name"):
        tg_name = await get_telegram_name(bot, user_id)
        if tg_name:
            user_data["tg_name"] = tg_name

    # Text se naam detect karo (override tg_name)
    detected_name = extract_name_from_text(user_text)
    if detected_name:
        user_data["name"] = detected_name

    # Mood + topic
    mood            = detect_mood(user_text)
    time_ctx        = get_time_context()
    detected_topic  = extract_topic(user_text)
    if detected_topic:
        user_data["last_topic"] = detected_topic

    # Prompt build + API call
    prompt  = build_prompt(history, user_data, user_text, mood, time_ctx)
    encoded = urllib.parse.quote(prompt)
    url     = f"{API_URL}{encoded}"

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

    # Lambi bot-jaisi reply? Sirf pehli line lo
    if len(reply) > 280:
        reply = reply.split("\n")[0].strip()

    # "Nia:" prefix hata do
    for prefix in ["nia:", "Nia:", "NIA:"]:
        if reply.startswith(prefix):
            reply = reply[len(prefix):].strip()

    # History save karo
    new_history = history + [
        {"role": "user",      "content": user_text},
        {"role": "assistant", "content": reply},
    ]
    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-(MAX_HISTORY * 2):]

    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "history":      new_history,
            "user_data":    user_data,
            "last_mood":    mood,
            "last_active":  datetime.now(),
        }},
        upsert=True
    )

    return reply

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

    chat        = update.effective_chat
    user_id     = msg.from_user.id if msg.from_user else None
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
        elif text.lower().startswith(("hi", "hey", "hello", "nia", "oye", "sun", "aye")):
            should_reply = True

    if not should_reply:
        return

    await context.bot.send_chat_action(chat.id, ChatAction.TYPING)

    # bot aur user_id pass karo naam fetch ke liye
    reply = await get_ai_reply(chat.id, text, bot=context.bot, user_id=user_id)
    await msg.reply_text(reply)

# -------- ECONOMY SUPPORT --------

async def ask_mistral_raw(system_prompt: str, user_input: str, max_tokens: int = 150) -> str | None:
    prompt  = system_prompt + "\nUser: " + user_input + "\nBot:"
    encoded = urllib.parse.quote(prompt)
    url     = f"{API_URL}{encoded}"

    try:
        resp = await http_client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return (
            data.get("reply") or data.get("response")
            or data.get("answer") or data.get("message")
            or str(data)
        )
    except Exception:
        return None

# -------- COMMANDS --------

async def chatbot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("hey 🙂 bol kya chal raha")


async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /ask kya chal raha")
        return

    text    = " ".join(context.args)
    user_id = update.message.from_user.id if update.message.from_user else None

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await get_ai_reply(update.effective_chat.id, text, bot=context.bot, user_id=user_id)
    await update.message.reply_text(reply)


async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """History + user data reset"""
    chat_id = update.effective_chat.id
    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"history": [], "user_data": {}}},
        upsert=True
    )
    await update.message.reply_text("theek hai fresh start 🙂")
