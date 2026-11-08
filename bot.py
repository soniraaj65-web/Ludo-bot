import os
import re
import asyncio
import sqlite3
import logging
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIGURATION ----------------
BOT_TOKEN = "9076286788:AAFcfibMCKsdMVvkkt3ajfacE6KRyLYAuLY"
ADMINS = ["raj1235567", "gotit", "virat"]
COMMISSION_PERCENT = 10
PORT = int(os.environ.get("PORT", 10000))

PINNED_SHEET_MSG_ID = None
LAST_ACTIVE_TABLE_MSG_ID = None
LAST_ACTIVE_ESTIMATE_MSG_ID = None

logging.basicConfig(level=logging.INFO)

# ---------------- 24/7 DUMMY SERVER FOR RENDER ----------------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Pure Sky King Table Master Live!")

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    server.serve_forever()

# ---------------- DATABASE ENGINE ----------------
def get_db():
    conn = sqlite3.connect("sky_all_in_one.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

db = get_db()
c = db.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    balance REAL DEFAULT 0.0,
    side_balance REAL DEFAULT 0.0,
    in_match INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_no INTEGER,
    host_id INTEGER,
    host_name TEXT,
    opp_id INTEGER,
    opp_name TEXT,
    amount REAL,
    mode TEXT,
    status TEXT,
    estimate_msg_id INTEGER,
    chat_id INTEGER
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    val INTEGER
)
""")
# Counter 0 se start rahega taaki agla match 1 bane
c.execute("INSERT OR IGNORE INTO meta (key, val) VALUES ('table_counter', 0)")
db.commit()

def get_next_counter(key_name):
    c.execute("SELECT val FROM meta WHERE key = ?", (key_name,))
    row = c.fetchone()
    current = row["val"] if row else 0
    nxt = current + 1
    c.execute("UPDATE meta SET val = ? WHERE key = ?", (nxt, key_name))
    db.commit()
    return nxt

def get_or_create_user(user):
    uid = user.id
    uname = (user.username or "").lower().replace("@", "")
    fname = user.first_name or "Player"

    c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, username, name, balance, side_balance, in_match) VALUES (?, ?, ?, 0.0, 0.0, 0)",
                  (uid, uname, fname))
        db.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        row = c.fetchone()
    else:
        c.execute("UPDATE users SET username = ?, name = ? WHERE user_id = ?", (uname, fname, uid))
        db.commit()
    return row

def get_user_by_username(uname_raw):
    clean = uname_raw.lower().replace("@", "").strip()
    c.execute("SELECT * FROM users WHERE LOWER(username) = ?", (clean,))
    return c.fetchone()

def update_bal(user_id, new_bal):
    c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (float(new_bal), user_id))
    db.commit()

def parse_amount(text):
    if not text:
        return None
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k", text, re.IGNORECASE)
    if k_match:
        return float(k_match.group(1)) * 1000.0
    num_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if num_match:
        return float(num_match.group(1))
    return None

def detect_mode(text):
    t = text.lower()
    if any(x in t for x in ["timer", "fast", "quick", "speed"]) or re.search(r"\b\d+\s*t\b", t):
        return "Timer"
    return "full"

def get_clickable_mention(user_or_row):
    if isinstance(user_or_row, sqlite3.Row) or isinstance(user_or_row, dict):
        uname = user_or_row["username"]
        uid = user_or_row["user_id"]
        fname = user_or_row["name"]
    else:
        uname = user_or_row.username
        uid = user_or_row.id
        fname = user_or_row.first_name or "Player"

    if uname:
        clean = uname.replace("@", "")
        return f"@{clean}"
    safe_name = (fname or "Player").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={uid}">{safe_name}</a>'

async def safe_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def delayed_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, delay=35):
    await asyncio.sleep(delay)
    await safe_delete(context, chat_id, message_id)

# ---------------- PINNED LEDGER ----------------
def generate_sheet():
    c.execute("SELECT name, username, balance FROM users WHERE balance != 0 ORDER BY balance DESC")
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) as live FROM games WHERE status = 'PLAYING'")
    live_count = c.fetchone()["live"]
    now_time = datetime.now().strftime("%I:%M %p")

    text = "👑 𝐓𝐇𝐄 𝐋𝐔𝐃𝐎 𝐄𝐌𝐏𝐈𝐑𝐄 • 𝐋𝐈𝐕𝐄 𝐋𝐄𝐃𝐆𝐄𝐑 👑\n"
    text += "──────────────────────────\n"
    text += "📋 Commission & Player Ledger:\n"
    text += "──────────────────────────\n"
    if not rows:
        text += "Sabhi accounts filhal clear hain (₹0.0).\n"
    else:
        for idx, r in enumerate(rows, start=1):
            disp = f"@{r['username']}" if r['username'] else r['name']
            dot = "🟢" if r["balance"] >= 0 else "🔴"
            text += f"{idx:02d}. {dot} {disp}: ₹{r['balance']:.1f}\n"

    text += "──────────────────────────\n"
    text += f"⚔️ Active Tables : {live_count}\n"
    text += f"⏱️ Updated At    : {now_time}\n"
    text += "──────────────────────────\n"
    text += "🔄 Automated Real-Time Settlement Engine"
    return text

async def sync_sheet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    global PINNED_SHEET_MSG_ID
    if PINNED_SHEET_MSG_ID:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=PINNED_SHEET_MSG_ID,
                text=generate_sheet()
            )
        except Exception:
            pass

# ---------------- BUTTON CALLBACKS ----------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_clean = (user.username or user.first_name or "").lower().replace("@", "")

    if query.data.startswith("details:"):
        uid = int(query.data.split(":")[1])
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        if r:
            disp = f"@{r['username']}" if r['username'] else r['name']
            await query.answer(
                f"👤 {disp}\n"
                f"💵 Balance: ₹{r['balance']:.1f}\n"
                f"📕 Side Balance: ₹{r['side_balance']:.1f}\n"
                f"⌛ In-Match: {'True' if r['in_match'] else 'False'}",
                show_alert=True
            )
        else:
            await query.answer("Record nahi mila!", show_alert=True)
        return

    data = query.data.split(":")
    action = data[0]
    gid = int(data[1])

    c.execute("SELECT * FROM games WHERE id = ?", (gid,))
    g = c.fetchone()
    if not g:
        await query.answer("Match nahi mila!", show_alert=True)
        return

    table_no = g["table_no"]
    h_name = g["host_name"]
    o_name = g["opp_name"]
    amt = float(g["amount"])
    est_msg_id = g["estimate_msg_id"]

    if action == "est":
        c.execute("SELECT balance FROM users WHERE user_id = ?", (g["host_id"],))
        h_bal = c.fetchone()["balance"]
        c.execute("SELECT balance FROM users WHERE user_id = ?", (g["opp_id"],))
        o_bal = c.fetchone()["balance"]
        await query.answer(
            f"📊 Action #{table_no} Live Balance:\n\n"
            f"{h_name}: ₹{h_bal:.1f}\n"
            f"{o_name}: ₹{o_bal:.1f}",
            show_alert=True
        )
        return

    is_admin = False
    try:
        cm = await context.bot.get_chat_member(query.message.chat_id, user.id)
        is_admin = (user_clean in ADMINS) or (cm.status in ["administrator", "creator"])
    except Exception:
        is_admin = user_clean in ADMINS

    if not is_admin:
        await query.answer("❌ Only Admins can settle or cancel matches!", show_alert=True)
        return

    if g["status"] != "PLAYING":
        await query.answer("⚠️ Match pehle se settled/closed hai!", show_alert=True)
        return

    # Cancel Match
    if action == "cancel":
        c.execute("SELECT balance FROM users WHERE user_id = ?", (g["host_id"],))
        h_bal = c.fetchone()["balance"]
        c.execute("SELECT balance FROM users WHERE user_id = ?", (g["opp_id"],))
        o_bal = c.fetchone()["balance"]

        new_h = h_bal + amt
        new_o = o_bal + amt

        update_bal(g["host_id"], new_h)
        update_bal(g["opp_id"], new_o)

        c.execute("UPDATE games SET status = 'CANCELED' WHERE id = ?", (gid,))
        c.execute("UPDATE users SET in_match = 0 WHERE user_id IN (?, ?)", (g["host_id"], g["opp_id"]))
        db.commit()

        await query.edit_message_reply_markup(reply_markup=None)

        if est_msg_id:
            try:
                card2_cancel = (
                    f"Action #{table_no} Canceled & Refunded! 🚫\n\n"
                    f"🟢 {h_name} refund:\n"
                    f"{h_bal:.1f} + {amt:.1f} ➔ {new_h:.1f}\n\n"
                    f"🟢 {o_name} refund:\n"
                    f"{o_bal:.1f} + {amt:.1f} ➔ {new_o:.1f}"
                )
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=est_msg_id,
                    text=card2_cancel,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Estimate", callback_data=f"est:{gid}")]])
                )
            except Exception:
                pass

        c_msg = await query.message.reply_text(f"🛑 Table #{table_no} Canceled!\nDono players ko ₹{amt:.1f} refund ho gaya.")
        await sync_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, c_msg.message_id, 30))
        await query.answer("Table Canceled!")
        return

    # Settle Winner
    if action in ["win1", "win2"]:
        win_id = g["host_id"] if action == "win1" else g["opp_id"]
        win_name = h_name if action == "win1" else o_name
        loser_id = g["opp_id"] if action == "win1" else g["host_id"]
        loser_name = o_name if action == "win1" else h_name

        tot = amt * 2.0
        cut = tot * (COMMISSION_PERCENT / 100.0)
        win_amt = tot - cut

        c.execute("SELECT balance FROM users WHERE user_id = ?", (win_id,))
        w_bal = c.fetchone()["balance"]
        new_w_bal = w_bal + win_amt
        update_bal(win_id, new_w_bal)

        c.execute("SELECT balance FROM users WHERE user_id = ?", (loser_id,))
        l_bal = c.fetchone()["balance"]

        c.execute("UPDATE games SET status = 'FINISHED' WHERE id = ?", (gid,))
        c.execute("UPDATE users SET in_match = 0 WHERE user_id IN (?, ?)", (g["host_id"], g["opp_id"]))
        db.commit()

        await query.edit_message_reply_markup(reply_markup=None)

        if est_msg_id:
            try:
                card2_settled = (
                    f"Action #{table_no} Settled! 🏆\n\n"
                    f"👑 Winner: {win_name}\n"
                    f"{w_bal:.1f} + {win_amt:.1f} ➔ {new_w_bal:.1f}\n\n"
                    f"👤 Opponent: {loser_name}\n"
                    f"Balance: {l_bal:.1f}"
                )
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=est_msg_id,
                    text=card2_settled,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Estimate", callback_data=f"est:{gid}")]])
                )
            except Exception:
                pass

        win_msg = await query.message.reply_text(
            f"🏆 TABLE #{table_no} WINNER! 🏆\n\n"
            f"👑 Winner: {win_name}\n"
            f"💰 Credited: ₹{win_amt:.1f} ({COMMISSION_PERCENT}% Cut)\n"
            f"💵 New Balance: ₹{new_w_bal:.1f}",
            parse_mode=ParseMode.HTML
        )
        await sync_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, win_msg.message_id, 30))
        await query.answer("Winner Declared!")
        return

# ---------------- PHOTO HANDLER (ROSE QR AUTO-DELETE 60s) ----------------
async def photo_cleaner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return

    sender = update.effective_user
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id

    sender_name = (sender.first_name or "").lower()
    sender_uname = (sender.username or "").lower()
    caption = (update.message.caption or "").lower()

    is_rose_or_qr = ("rose" in sender_name or "rose" in sender_uname or sender.is_bot or "qr" in caption)
    if is_rose_or_qr:
        asyncio.create_task(delayed_delete(context, chat_id, msg_id, 60))

# ---------------- HELPER: CREATE AND POST TABLE ----------------
async def build_and_post_table(context: ContextTypes.DEFAULT_TYPE, chat_id, host_data, opp_data, amt, mode, clean_msg_ids):
    global LAST_ACTIVE_TABLE_MSG_ID, LAST_ACTIVE_ESTIMATE_MSG_ID

    h_id = host_data["user_id"] if isinstance(host_data, (sqlite3.Row, dict)) else host_data.id
    o_id = opp_data["user_id"] if isinstance(opp_data, (sqlite3.Row, dict)) else opp_data.id

    c.execute("SELECT balance FROM users WHERE user_id = ?", (h_id,))
    h_bal = float(c.fetchone()["balance"])
    c.execute("SELECT balance FROM users WHERE user_id = ?", (o_id,))
    o_bal = float(c.fetchone()["balance"])

    h_disp = get_clickable_mention(host_data)
    o_disp = get_clickable_mention(opp_data)

    # THRESHOLD CHECK
    if h_bal < amt or o_bal < amt:
        h_dot = "🟢" if h_bal >= amt else "🔴"
        o_dot = "🟢" if o_bal >= amt else "🔴"

        fail_card = (
            "🔴 Failed because one of the users would have a balance below the minimum threshold (0).\n\n"
            f"{h_dot} {h_disp} estimate:\n"
            f"{h_bal:.1f} - {amt:.1f} ➔ {(h_bal - amt):.1f}\n\n"
            f"{o_dot} {o_disp} estimate:\n"
            f"{o_bal:.1f} - {amt:.1f} ➔ {(o_bal - amt):.1f}"
        )
        err = await context.bot.send_message(chat_id=chat_id, text=fail_card, parse_mode=ParseMode.HTML)
        asyncio.create_task(delayed_delete(context, chat_id, err.message_id, 25))
        return

    # Deduct Stakes
    new_h_bal = h_bal - amt
    new_o_bal = o_bal - amt
    update_bal(h_id, new_h_bal)
    update_bal(o_id, new_o_bal)

    t_num = get_next_counter("table_counter")

    # Smooth Multi-Step Animation Loader
    loader_msg = await context.bot.send_message(chat_id=chat_id, text="🎲 Rolling dice . . .")
    await asyncio.sleep(0.5)
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=loader_msg.message_id, text="⏳ Generating Match Slip . . .")
    except Exception:
        pass
    await asyncio.sleep(0.5)

    c.execute("INSERT INTO games (table_no, host_id, host_name, opp_id, opp_name, amount, mode, status, estimate_msg_id, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?, 'PLAYING', NULL, ?)",
              (t_num, h_id, h_disp, o_id, o_disp, amt, mode, chat_id))
    gid = c.lastrowid
    c.execute("UPDATE users SET in_match = 1 WHERE user_id IN (?, ?)", (h_id, o_id))
    db.commit()

    card1_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Cancel This Table", callback_data=f"cancel:{gid}")],
        [
            InlineKeyboardButton("🏆 #1 Won...", callback_data=f"win1:{gid}"),
            InlineKeyboardButton("🏆 #2 Won...", callback_data=f"win2:{gid}")
        ]
    ])
    card1_text = (
        f"🎲 Table No. {t_num}\n\n"
        f"(1). {h_disp}\n\n"
        f"(2). {o_disp}\n\n"
        f"{int(amt)} ✅ {mode}"
    )

    card2_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Estimate", callback_data=f"est:{gid}")]])
    card2_text = (
        f"Action #{t_num} successful! ✅\n\n"
        f"🟢 {h_disp} estimate:\n"
        f"{h_bal:.1f} - {amt:.1f} ➔ {new_h_bal:.1f}\n\n"
        f"🟢 {o_disp} estimate:\n"
        f"{o_bal:.1f} - {amt:.1f} ➔ {new_o_bal:.1f}"
    )

    await safe_delete(context, chat_id, loader_msg.message_id)

    if LAST_ACTIVE_TABLE_MSG_ID:
        asyncio.create_task(delayed_delete(context, chat_id, LAST_ACTIVE_TABLE_MSG_ID, 30))
    if LAST_ACTIVE_ESTIMATE_MSG_ID:
        asyncio.create_task(delayed_delete(context, chat_id, LAST_ACTIVE_ESTIMATE_MSG_ID, 30))

    sent_card1 = await context.bot.send_message(chat_id=chat_id, text=card1_text, reply_markup=card1_kb, parse_mode=ParseMode.HTML)
    LAST_ACTIVE_TABLE_MSG_ID = sent_card1.message_id

    sent_card2 = await context.bot.send_message(chat_id=chat_id, text=card2_text, reply_markup=card2_kb, parse_mode=ParseMode.HTML)
    LAST_ACTIVE_ESTIMATE_MSG_ID = sent_card2.message_id

    c.execute("UPDATE games SET estimate_msg_id = ? WHERE id = ?", (sent_card2.message_id, gid))
    db.commit()

    for mid in clean_msg_ids:
        asyncio.create_task(delayed_delete(context, chat_id, mid, 30))
    await sync_sheet(chat_id, context)

# ---------------- MAIN ROUTER ----------------
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PINNED_SHEET_MSG_ID
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip()
    text = raw.lower()
    sender = update.effective_user
    chat_id = update.effective_chat.id

    sender_clean = (sender.username or sender.first_name or "").lower().replace("@", "")
    is_admin = False
    try:
        cm = await context.bot.get_chat_member(chat_id, sender.id)
        is_admin = (sender_clean in ADMINS) or (cm.status in ["administrator", "creator"])
    except Exception:
        is_admin = sender_clean in ADMINS

    clean_cmd = text.lstrip("/").strip()

    # 1. LIVE CALCULATOR (7700-6175 = 1525)
    calc_match = re.match(r"^(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)$", text)
    if calc_match:
        n1 = float(calc_match.group(1))
        op = calc_match.group(2)
        n2 = float(calc_match.group(3))
        res = 0
        if op == '+': res = n1 + n2
        elif op == '-': res = n1 - n2
        elif op == '*': res = n1 * n2
        elif op == '/': res = n1 / n2 if n2 != 0 else 0
        res_str = f"{int(res)}" if res.is_integer() else f"{res:.2f}"
        calc_msg = await update.message.reply_text(f"{raw} = {res_str}")
        asyncio.create_task(delayed_delete(context, chat_id, calc_msg.message_id, 40))
        return

    # 2. PIN SHEET
    if clean_cmd in ["pinsheet", "sheet", "ledger"] and is_admin:
        msg = await update.message.reply_text(generate_sheet())
        try:
            await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
            PINNED_SHEET_MSG_ID = msg.message_id
            asyncio.create_task(safe_delete(context, chat_id, update.message.message_id))
        except Exception:
            pass
        return

    # 3. BALANCE ADD
    add_match = re.match(r"^(?:add|addbal|\+|credit)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and add_match and is_admin:
        target = update.message.reply_to_message.from_user
        if target:
             amt = parse_amount(add_match.group(1))
            if amt:
                user_row = get_or_create_user(target)
                old_bal = float(user_row["balance"])
                new_bal = old_bal + amt
                update_bal(target.id, new_bal)

                t_disp = get_clickable_mention(target)
                card = (
                    "Balance Added ✅\n\n"
                    f"💵 New Balance: {new_bal:.1f}\n"
                    f"🤠 User: {t_disp}\n\n"
                    f"changes: {old_bal:.1f} + {amt:.1f}"
                )
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data=f"details:{target.id}")]])
                sent = await update.message.reply_text(card, reply_markup=kb, parse_mode=ParseMode.HTML)
                await sync_sheet(chat_id, context)
                asyncio.create_task(delayed_delete(context, chat_id, sent.message_id, 60))
                return

    # 4. BALANCE MINUS / WITHDRAW (w, withdrawal, payout, cut)
    cut_match = re.match(r"^(?:cut|cutbal|-|debit|w|wd|withdraw|withdrawal|payout)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and cut_match and is_admin:
        target = update.message.reply_to_message.from_user
        if target:
            amt = parse_amount(cut_match.group(1))
            if amt:
                user_row = get_or_create_user(target)
                old_bal = float(user_row["balance"])
                new_bal = old_bal - amt
                update_bal(target.id, new_bal)

                t_disp = get_clickable_mention(target)
                card = (
                    "Balance Minus ⛔\n\n"
                    f"💵 New Balance: {new_bal:.1f}\n"
                    f"🤠 User: {t_disp}\n\n"
                    f"changes: {old_bal:.1f} - {amt:.1f}"
                )
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data=f"details:{target.id}")]])
                sent = await update.message.reply_text(card, reply_markup=kb, parse_mode=ParseMode.HTML)
                await sync_sheet(chat_id, context)
                asyncio.create_task(delayed_delete(context, chat_id, sent.message_id, 60))
                return

    # 5. USER INFO
    if clean_cmd in ["info", "bal", "balance", "mybal"]:
        target = update.message.reply_to_message.from_user if (update.message.reply_to_message and is_admin) else sender
        user_row = get_or_create_user(target)
        t_disp = get_clickable_mention(target)

        info_card = (
            f"💰 {t_disp}'s INFO:\n\n"
            f"💵 Balance : {user_row['balance']:.1f}\n"
            f"📕 Side Balance: {user_row['side_balance']:.1f}\n"
            f"⌛ In-Match: {'True' if user_row['in_match'] else 'False'}"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data=f"details:{target.id}")]])
        sent = await update.message.reply_text(info_card, reply_markup=kb, parse_mode=ParseMode.HTML)
        asyncio.create_task(delayed_delete(context, chat_id, sent.message_id, 30))
        asyncio.create_task(delayed_delete(context, chat_id, update.message.message_id, 30))
        return

    # 6. TABLE CREATION - STRICT ADMIN CONTROL
    # Form 1: Admin Direct Command: "@user1 @user2 play 200" ya "play @user1 @user2 200"
    if is_admin and ("play" in text or "table" in text or "lga" in text):
        mentions = re.findall(r"@([a-zA-Z0-9_]+)", raw)
        amt = parse_amount(raw)
        if len(mentions) >= 2 and amt and amt >= 10.0:
            u1 = get_user_by_username(mentions[0])
            u2 = get_user_by_username(mentions[1])
            if u1 and u2 and u1["user_id"] != u2["user_id"]:
                mode = detect_mode(raw)
                await build_and_post_table(context, chat_id, u1, u2, amt, mode, [update.message.message_id])
                return

    # Form 2: Admin Swipe-Reply Confirmation ("200 ✅ full")
    if is_admin and update.message.reply_to_message and ("✅" in raw or "full" in text):
        replied_msg = update.message.reply_to_message
        amt = parse_amount(raw) or parse_amount(replied_msg.text or "")
        if amt and amt >= 10.0:
            # Agar replied message khud kisi aur ke message ka reply hai
            if replied_msg.reply_to_message:
                host = replied_msg.reply_to_message.from_user
                opp = replied_msg.from_user
                if host and opp and host.id != opp.id:
                    get_or_create_user(host)
                    get_or_create_user(opp)
                    mode = detect_mode(raw + " " + (replied_msg.text or ""))
                    clean_ids = [update.message.message_id, replied_msg.message_id, replied_msg.reply_to_message.message_id]
                    await build_and_post_table(context, chat_id, host, opp, amt, mode, clean_ids)
                    return

def main():
    Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, photo_cleaner))
    app.add_handler(MessageHandler(filters.TEXT, router))
    logging.info("Sky King Engine Live!")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
