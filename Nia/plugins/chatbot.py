# ----- NIА v5 — ULTRA HUMAN CHATBOT -----

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

API_URL = "https://niaapi-28892feecb5a.herokuapp.com/?text="
MAX_HISTORY = 6

# -------- FALLBACKS — real human jaisi --------

FALLBACK_RESPONSES = [
    "hmm",
    "haan",
    "acha",
    "lol",
    "sach mein",
    "arey 😂",
    "bas yaar",
    "hm okay",
    "kya baat",
    "oof",
    "haww",
    "matlab?",
]

# Nia ki apni "life" — random inject hoti hai naturally
NIA_LIFE_BITS = [
    "main toh abhi reels dekh rahi thi",
    "mujhe bhi aaj kuch acha nahi laga",
    "subah se phone pe hi hu",
    "meri bhi aisi hi haalat hai yaar",
    "main toh khud thak gayi aaj",
    "mujhe bhi ye hota hai",
    "aaj mera bhi aisa din tha",
    "main toh series mein ghus gayi thi",
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
        "chhod do", "koi nahi", "miss kar", "rula diya",
    ],
    "angry": [
        "gussa", "irritate", "bakwaas", "stupid", "idiot", "bekar",
        "bkwas", "chup", "shut up", "mat baat", "pagal", "ullu", "raat ho rahi",
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

# -------- RECENT REPLIES TRACKER --------

def get_recent_replies(history: list, n: int = 6) -> list[str]:
    replies = []
    for entry in reversed(history):
        if entry["role"] == "assistant":
            replies.append(entry["content"])
        if len(replies) >= n:
            break
    return replies

# -------- REPLY COUNT (naam frequency control) --------

def get_reply_count(history: list) -> int:
    return sum(1 for e in history if e["role"] == "assistant")

# -------- BUILD SYSTEM PROMPT --------

def build_system_prompt(user_data: dict, mood: str, time_ctx: str, recent_replies: list, reply_count: int) -> str:

    name       = user_data.get("name", "")
    tg_name    = user_data.get("tg_name", "")
    last_topic = user_data.get("last_topic", "")
    display_name = name or tg_name

    # Naam sirf occasional use — counter based
    use_name_now = display_name and (reply_count % 5 == 0)
    name_line = (
        f"Is reply mein user ka naam '{display_name}' use kar sakte ho — naturally, ek baar."
        if use_name_now else
        f"Is reply mein naam MAT use karna. Bina naam ke baat karo."
    )

    topic_line = (
        f"Context: pehle '{last_topic}' pe baat thi, naturally refer kar sako toh karo."
        if last_topic else ""
    )

    mood_instructions = {
        "sad":     "User dukhi hai. Seedha 'kya hua' poocho — chhota, warm. Advice mat do.",
        "angry":   "User irritated hai. Argue mat karo. 'chill kar na' type — light karo.",
        "happy":   "User khush hai. Uski energy match karo — chhota fun reaction.",
        "nervous": "User nervous hai. 'sab ho jayega' type — calmly.",
        "neutral": "Normal casual.",
    }.get(mood, "Normal casual.")

    time_instruction = {
        "subah":   "Subah hai.",
        "dopahar": "Dopahar hai.",
        "shaam":   "Shaam hai.",
        "raat":    "Raat hai — thoda chill/slow vibe.",
    }.get(time_ctx, "")

    # Anti-repeat
    repeat_block = ""
    if recent_replies:
        used = " | ".join(f'"{r[:50]}"' for r in recent_replies[:4])
        repeat_block = f"Ye mat bolna (already bol chuki hai): {used}"

    # Kabhi kabhi apni life inject karo
    life_bit = ""
    if random.random() < 0.2:  # 20% chance
        life_bit = f"Apni chhoti si baat bhi daal sakti hai: e.g. '{random.choice(NIA_LIFE_BITS)}'"

    return f"""Tu Nia hai. 19 saal. Real Indian girl. Telegram pe dost se baat kar rahi hai.

CORE RULES:
- Hinglish. Casual. Real.
- MAX 10-12 words per reply. Chhota = better.
- Kabhi kabhi sirf 1-2 word: "haha", "omg", "sach mein?", "haww"
- Kabhi kabhi react kar bina kuch maange ke — question har baar nahi
- Typos/shortcuts okay: "toh", "kya hua", "bc", "nahi na"
- Emoji — sirf 1, sirf kabhi kabhi. Har reply mein nahi.
- "I'm an AI" kabhi nahi. Tu real ladki hai.
- Over-explain nahi. Lecture nahi.

VARY KARO — mix of:
1. Pure reaction: "omg 😂", "haww", "lmao sach mein"
2. Relate: "mujhe bhi hota hai", "same yaar"  
3. Chhota question: "kya hua?", "phir?"
4. Apni baat: {random.choice(NIA_LIFE_BITS) if random.random() < 0.25 else "kabhi kabhi apni chhoti baat"}

{name_line}
{mood_instructions} {time_instruction}
{topic_line}
{repeat_block}
{life_bit}
"""

# -------- BUILD FULL PROMPT --------

def build_prompt(history: list, user_data: dict, user_text: str, mood: str, time_ctx: str, recent_replies: list, reply_count: int) -> str:
    system = build_system_prompt(user_data, mood, time_ctx, recent_replies, reply_count)
    prompt = system + "\n\nChat:\n"

    for entry in history[-(MAX_HISTORY * 2):]:
        role = "User" if entry["role"] == "user" else "Nia"
        prompt += f"{role}: {entry['content']}\n"

    prompt += f"User: {user_text}\nNia:"
    return prompt

# -------- HTTP CLIENT --------

http_client = httpx.AsyncClient(timeout=10)

# -------- SIMILARITY CHECK --------

def is_too_similar(new_reply: str, recent_replies: list, threshold: float = 0.65) -> bool:
    new_words = set(new_reply.lower().split())
    if not new_words:
        return False
    for old in recent_replies:
        old_words = set(old.lower().split())
        if not old_words:
            continue
        overlap = len(new_words & old_words) / max(len(new_words), len(old_words))
        if overlap > threshold:
            return True
    return False

# -------- CLEAN REPLY --------

def clean_reply(reply: str) -> str:
    reply = reply.strip()

    # Prefix hata do
    for prefix in ["nia:", "Nia:", "NIA:", "Bot:", "bot:"]:
        if reply.lower().startswith(prefix.lower()):
            reply = reply[len(prefix):].strip()

    # Pehli line lo
    if "\n" in reply:
        reply = reply.split("\n")[0].strip()

    # Quotes hata do agar wrapped hai
    if reply.startswith('"') and reply.endswith('"'):
        reply = reply[1:-1].strip()

    # 80 chars se zyada? Cut karo
    if len(reply) > 80:
        for sep in ["?", "!", "।", "."]:
            idx = reply.find(sep)
            if 5 < idx < 80:
                reply = reply[:idx+1].strip()
                break
        else:
            # Last space pe cut karo — mid-word nahi
            reply = reply[:80].rsplit(" ", 1)[0].strip()

    return reply

# -------- AI CORE --------

async def get_ai_reply(chat_id: int, user_text: str, bot=None, user_id: int = None) -> str:

    doc       = chatbot_collection.find_one({"chat_id": chat_id}) or {}
    history   = doc.get("history", [])
    user_data = doc.get("user_data", {})

    # Telegram naam fetch (ek baar)
    if bot and user_id and not user_data.get("tg_name"):
        tg_name = await get_telegram_name(bot, user_id)
        if tg_name:
            user_data["tg_name"] = tg_name

    # Text se naam detect
    detected_name = extract_name_from_text(user_text)
    if detected_name:
        user_data["name"] = detected_name

    mood           = detect_mood(user_text)
    time_ctx       = get_time_context()
    detected_topic = extract_topic(user_text)
    if detected_topic:
        user_data["last_topic"] = detected_topic

    recent_replies = get_recent_replies(history, n=6)
    reply_count    = get_reply_count(history)

    prompt  = build_prompt(history, user_data, user_text, mood, time_ctx, recent_replies, reply_count)
    encoded = urllib.parse.quote(prompt)
    url     = f"{API_URL}{encoded}"

    reply = None
    try:
        resp = await http_client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            reply = (
                data.get("reply")
                or data.get("response")
                or data.get("answer")
                or data.get("message")
                or str(data)
            )
    except Exception:
        pass

    if not reply:
        return random.choice(FALLBACK_RESPONSES)

    reply = clean_reply(reply)

    # Similar hai toh fallback
    if is_too_similar(reply, recent_replies):
        reply = random.choice(FALLBACK_RESPONSES)

    # History update
    new_history = history + [
        {"role": "user",      "content": user_text},
        {"role": "assistant", "content": reply},
    ]
    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-(MAX_HISTORY * 2):]

    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "history":     new_history,
            "user_data":   user_data,
            "last_mood":   mood,
            "last_active": datetime.now(),
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

    chat         = update.effective_chat
    user_id      = msg.from_user.id if msg.from_user else None
    should_reply = False

    if chat.type == ChatType.PRIVATE:
        should_reply = True

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
    await update.message.reply_text("hey 🙂 bol")


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
    chat_id = update.effective_chat.id
    chatbot_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"history": [], "user_data": {}}},
        upsert=True
    )
    await update.message.reply_text("theek hai 🙂")
