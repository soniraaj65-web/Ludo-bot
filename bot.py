import os
import re
import asyncio
import sqlite3
import logging
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIGURATION ----------------
BOT_TOKEN = "9076286788:AAFcfibMCKsdMVvkkt3ajfacE6KRyLYAuLY"
ADMINS = ["raj1235567"]
UPI_ID = "choudharyvikash4705-2@okicici"
PAYEE_NAME = "Vikash Choudhary"
COMMISSION_PERCENT = 10
PORT = int(os.environ.get("PORT", 10000))

PINNED_SHEET_MSG_ID = None
USER_LAST_BET_MSG = {}
LAST_ACTIVE_TABLE_MSG_ID = None

BAD_WORDS = [
    "mc", "bc", "bhosdike", "chutiya", "madarchod", "gandu", 
    "lauda", "lodu", "behenchod", "harami", "bkl", "bsdk", "randi",
    "chudai", "madarjat", "bhen ke lode", "mkl"
]

logging.basicConfig(level=logging.INFO)

# ---------------- DUMMY HTTP SERVER (RENDER 24/7) ----------------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Ludo King Live Interactive Engine Running!")

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    server.serve_forever()

# ---------------- DATABASE SETUP ----------------
def get_db():
    conn = sqlite3.connect("ludo_data.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

db = get_db()
c = db.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
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
    host TEXT,
    opponent TEXT,
    amount REAL,
    mode TEXT DEFAULT 'full',
    status TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    val INTEGER
)
""")
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

def get_user_data(username, fallback_name="Player"):
    username = username.lower().replace("@", "")
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT OR REPLACE INTO users (username, name, balance, side_balance, in_match) VALUES (?, ?, 0.0, 0.0, 0)", (username, fallback_name))
        db.commit()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = c.fetchone()
    return row

def update_user_balance(username, new_bal, name=None):
    username = username.lower().replace("@", "")
    if name:
        c.execute("UPDATE users SET balance = ?, name = ? WHERE username = ?", (float(new_bal), name, username))
    else:
        c.execute("UPDATE users SET balance = ? WHERE username = ?", (float(new_bal), username))
    db.commit()

def parse_amount(text):
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k", text, re.IGNORECASE)
    if k_match:
        return float(k_match.group(1)) * 1000.0
    num_match = re.search(r"\b(\d+)\b", text)
    if num_match:
        return float(num_match.group(1))
    return None

def detect_mode(text):
    t_lower = text.lower()
    if any(k in t_lower for k in ["t", "timer", "quick", "fast", "speed"]):
        return "timer"
    return "full"

# ---------------- AUTO-CLEAN UTILITIES ----------------
async def safe_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def delayed_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, delay_seconds=30):
    await asyncio.sleep(delay_seconds)
    await safe_delete(context, chat_id, message_id)

async def send_self_destruct_warning(context: ContextTypes.DEFAULT_TYPE, chat_id, text, delay=30):
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        asyncio.create_task(delayed_delete(context, chat_id, msg.message_id, delay))
    except Exception as e:
        logging.error(f"Warning send error: {e}")

# ---------------- PROFESSIONAL LIVE BALANCE SHEET ----------------
def generate_sheet_text():
    c.execute("SELECT name, username, balance FROM users WHERE balance != 0 ORDER BY balance DESC")
    rows = c.fetchall()
    
    c.execute("SELECT COUNT(*) AS total_live FROM games WHERE status = 'PLAYING'")
    live_matches = c.fetchone()["total_live"]

    total_balance = sum(r["balance"] for r in rows)
    current_time = datetime.now().strftime("%I:%M %p")
    
    text = (
        "👑 **THE LUDO EMPIRE • OFFICIAL LEDGER** 👑\n"
        "════════════════════════════\n"
        "📈 **LIVE PLAYER BALANCES**\n"
        "────────────────────────────\n"
    )
    
    if not rows:
        text += "• _Filhal sabhi balances clear hain (0.0)._\n"
    else:
        for idx, r in enumerate(rows, start=1):
            disp_name = r["name"] or r["username"]
            bal = r["balance"]
            tag = "🟢" if bal >= 0 else "🔴"
            text += f"`{idx:02d}.` {tag} **{disp_name}** (`@{r['username']}`): **₹{bal:.1f}**\n"
            
    text += (
        "────────────────────────────\n"
        f"💰 **Total Club Reserve :** ₹{total_balance:.1f}\n"
        f"🎲 **Active Tables Live  :** {live_matches}\n"
        f"⏱️ **Last Synced At      :** {current_time}\n"
        "════════════════════════════\n"
        "🔄 _Sheet is real-time automated & auto-synced._"
    )
    return text

async def sync_pinned_sheet(chat_id, context: ContextTypes.DEFAULT_TYPE):
    global PINNED_SHEET_MSG_ID
    if PINNED_SHEET_MSG_ID:
        try:
            sheet_content = generate_sheet_text()
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=PINNED_SHEET_MSG_ID,
                text=sheet_content,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Error auto-updating pinned sheet: {e}")

# ---------------- QR HELPER ----------------
async def send_qr_message(chat_id, context: ContextTypes.DEFAULT_TYPE, reply_to_id=None):
    caption = (
        f"💳 *OFFICIAL PAYMENT QR*\n\n"
        f"• *Name:* {PAYEE_NAME}\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        f"⚠️ Screenshot chat me bhejein (Screenshot delete nahi hoga)."
    )
    if os.path.exists("qr.jpg"):
        with open("qr.jpg", "rb") as p:
            sent = await context.bot.send_photo(chat_id=chat_id, photo=p, caption=caption, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    else:
        sent = await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    
    asyncio.create_task(delayed_delete(context, chat_id, sent.message_id, 30))

# ---------------- WELCOME HANDLER ----------------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.old_chat_member.status in ["left", "kicked"] and result.new_chat_member.status in ["member", "administrator"]:
        new_user = result.new_chat_member.user
        mention = f"@{new_user.username}" if new_user.username else new_user.first_name
        
        welcome_text = (
            f"👋 *WELCOME TO THE LUDO EMPIRE, {mention}!* 🎲\n\n"
            "✨ *Direct table lagane ke liye amount likhein:*\n"
            "👉 `50` | `100` | `500 full` | `50 t` | `1k` | `5kff`\n\n"
            "• Challenge par reply karke `ok` ya `lga` karein\n"
            "• Info check karne ke liye: `info`\n"
            "• QR/Deposit ke liye: `qr`"
        )
        sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, parse_mode="Markdown")
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))

# ---------------- PHOTO HANDLER (PERMANENT SCREENSHOTS) ----------------
async def handle_photo_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Screenshots are never auto-deleted to preserve transaction proof
    pass

# ---------------- INLINE BUTTON CALLBACK (WINNER 1, WINNER 2, CANCEL) ----------------
async def table_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_clean = (user.username or "").lower().replace("@", "")

    # Sirf Admin buttons dabakar match result ya cancel kar sakta hai
    if user_clean not in ADMINS:
        await query.answer("❌ Only Admins can take table action!", show_alert=True)
        return

    data = query.data.split(":")
    action = data[0]
    game_id = int(data[1])

    c.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    game = c.fetchone()
    if not game or game["status"] != "PLAYING":
        await query.answer("⚠️ This match is already finished or canceled!", show_alert=True)
        return

    table_no = game["table_no"]
    host = game["host"]
    opponent = game["opponent"]
    amt = float(game["amount"])

    # 1. CANCEL BUTTON LOGIC
    if action == "cancel":
        # Dono players ko unka deducted balance refund
        host_rec = get_user_data(host)
        opp_rec = get_user_data(opponent)

        update_user_balance(host, host_rec["balance"] + amt)
        update_user_balance(opponent, opp_rec["balance"] + amt)

        c.execute("UPDATE games SET status = 'CANCELED' WHERE id = ?", (game_id,))
        c.execute("UPDATE users SET in_match = 0 WHERE username IN (?, ?)", (host.lower(), opponent.lower()))
        db.commit()

        await query.edit_message_reply_markup(reply_markup=None)
        cancel_msg = await query.message.reply_text(f"🚫 **Table No. {table_no} Canceled!**\nBalance refunded to @{host} and @{opponent}.")
        await sync_pinned_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, cancel_msg.message_id, 30))
        await query.answer("Table Canceled & Refunded!")
        return

    # 2. WINNER 1 OR WINNER 2 LOGIC
    if action in ["win1", "win2"]:
        winner_uname = host if action == "win1" else opponent
        loser_uname = opponent if action == "win1" else host

        tot_pot = amt * 2.0
        commission = tot_pot * (COMMISSION_PERCENT / 100.0)
        win_amt = tot_pot - commission

        user_rec = get_user_data(winner_uname)
        new_bal = user_rec["balance"] + win_amt
        update_user_balance(winner_uname, new_bal)

        c.execute("UPDATE games SET status = 'FINISHED' WHERE id = ?", (game_id,))
        c.execute("UPDATE users SET in_match = 0 WHERE username IN (?, ?)", (host.lower(), opponent.lower()))
        db.commit()

        await query.edit_message_reply_markup(reply_markup=None)
        win_msg = await query.message.reply_text(
            f"🏆 **WINNER CONFIRMED (Table No. {table_no})!**\n\n"
            f"Winner: @{winner_uname}\n"
            f"Pot: ₹{tot_pot:.1f}\n"
            f"Credited: **₹{win_amt:.1f}** (10% Commission Cut) ✅"
        )
        await sync_pinned_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, win_msg.message_id, 30))
        await query.answer(f"@{winner_uname} won!")
        return

# ---------------- MAIN ZERO-SLASH PROCESSING ENGINE ----------------
async def zero_slash_table_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PINNED_SHEET_MSG_ID, USER_LAST_BET_MSG, LAST_ACTIVE_TABLE_MSG_ID
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip()
    text = raw_text.lower()
    sender = update.effective_user
    sender_name = sender.first_name or "Player"
    sender_username = sender.username or sender_name
    sender_clean = (sender.username or "").lower().replace("@", "")

    clean_cmd = text.lstrip("/").strip()

    # 1. PIN SHEET TRIGGER (Admin)
    if clean_cmd in ["pinsheet", "pin sheet", "sheet", "ledger", "balancesheet"] and sender_clean in ADMINS:
        sheet_text = generate_sheet_text()
        sent_msg = await update.message.reply_text(sheet_text, parse_mode="Markdown")
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=sent_msg.message_id,
                disable_notification=True
            )
            PINNED_SHEET_MSG_ID = sent_msg.message_id
            await send_self_destruct_warning(context, update.effective_chat.id, "📌 *Professional Ledger successfully pinned!*", 30)
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
        except Exception as e:
            logging.error(f"Pin error: {e}")
        return

    # 2. REAL TELEGRAM GROUP PERMISSION LOCK / UNLOCK
    if clean_cmd in ["lock", "close", "band"]:
        if sender_clean in ADMINS:
            try:
                await context.bot.set_chat_permissions(
                    chat_id=update.effective_chat.id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                await send_self_destruct_warning(context, update.effective_chat.id, "🔒 *GROUP LOCKED!* Admin ke alawa koi message nahi bhej sakta.", 30)
            except Exception:
                await send_self_destruct_warning(context, update.effective_chat.id, "⚠️ Bot ko 'Restrict Members' admin permission dein!", 30)
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
            return

    elif clean_cmd in ["unlock", "open group", "chalu", "start", "khula"]:
        if sender_clean in ADMINS:
            try:
                await context.bot.set_chat_permissions(
                    chat_id=update.effective_chat.id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_photos=True,
                        can_send_other_messages=True
                    )
                )
                await send_self_destruct_warning(context, update.effective_chat.id, "🔓 *GROUP UNLOCKED!* Members ab message bhej sakte hain.", 30)
            except Exception:
                await send_self_destruct_warning(context, update.effective_chat.id, "⚠️ Bot ko 'Restrict Members' admin permission dein!", 30)
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
            return

    # 3. ANTI-GALI & ANTI-LINK FILTER
    if sender_clean not in ADMINS:
        words = text.split()
        if any(bad in words or bad in text for bad in BAD_WORDS) or ("http://" in text or "https://" in text or "t.me/" in text):
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
            await send_self_destruct_warning(context, update.effective_chat.id, f"⚠️ {sender_name}, abusive bhasha/links allowed nahi hain!", 30)
            return

    # 4. ADMIN REPLY BALANCE ADD (Deleted after 30s)
    add_match = re.match(r"^(?:/)?(?:add|addbal|\+|ubdet|update bal|update|credit)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and add_match and sender_clean in ADMINS:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_uname = replied_user.username or replied_user.first_name
            target_name = replied_user.first_name or target_uname
            amt = parse_amount(add_match.group(1))
            if amt and amt > 0:
                user_rec = get_user_data(target_uname, target_name)
                old_bal = float(user_rec["balance"])
                new_bal = old_bal + amt
                update_user_balance(target_uname, new_bal, target_name)

                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data="none")]])
                msg = (
                    f"**Balance Added ✅**\n\n"
                    f"💳 **New Balance:** {new_bal}\n"
                    f"👤 **User:** {target_name}\n\n"
                    f"_changes: {old_bal} + {amt}_"
                )
                sent = await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                await sync_pinned_sheet(update.effective_chat.id, context)
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
                return

    # 5. ADMIN REPLY BALANCE CUT (Deleted after 30s)
    cut_match = re.match(r"^(?:/)?(?:cut|cutbal|-|debit|kat)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and cut_match and sender_clean in ADMINS:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_uname = replied_user.username or replied_user.first_name
            target_name = replied_user.first_name or target_uname
            amt = parse_amount(cut_match.group(1))
            if amt and amt > 0:
                user_rec = get_user_data(target_uname, target_name)
                old_bal = float(user_rec["balance"])
                new_bal = old_bal - amt
                update_user_balance(target_uname, new_bal, target_name)

                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data="none")]])
                msg = (
                    f"**Balance Deducted ✂️**\n\n"
                    f"💳 **New Balance:** {new_bal}\n"
                    f"👤 **User:** {target_name}\n\n"
                    f"_changes: {old_bal} - {amt}_"
                )
                sent = await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                await sync_pinned_sheet(update.effective_chat.id, context)
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
                return

    # 6. USER INFO CARD
    if clean_cmd in ["info", "bal", "balance", "mybal", "profile"]:
        user_rec = get_user_data(sender_username, sender_name)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data="none")]])
        msg = (
            f"💰 **{user_rec['name']}'s INFO:**\n\n"
            f"💳 **Balance :** {user_rec['balance']}\n"
            f"📕 **Side Balance:** {user_rec['side_balance']}\n"
            f"⏳ **In-Match:** {'True' if user_rec['in_match'] else 'False'}"
        )
        sent = await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
        return

    # 7. QR CODE
    if clean_cmd in ["qr", "payment", "scanner", "pay", "upi", "paisa"]:
        await send_qr_message(update.effective_chat.id, context, update.message.message_id)
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
        return

       # 8. WITHDRAWAL
    wd_match = re.match(r"^(?:/)?(?:withdraw|wd|nikalo)\s+(\d+)\s+([a-zA-Z0-9.\-_+@]+)$", text)
    if wd_match:
        amt = float(wd_match.group(1))
        upi_id = wd_match.group(2)
        user_rec = get_user_data(sender_username, sender_name)
        if user_rec["balance"] < amt:
            await send_self_destruct_warning(context, update.effective_chat.id, f"❌ Low Balance! Aapka balance ₹{user_rec['balance']} hai.", 30)
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
            return

        update_user_balance(sender_username, user_rec["balance"] - amt)
        await sync_pinned_sheet(update.effective_chat.id, context)
        msg = (
            f"🔔 **WITHDRAWAL REQUEST**\n\n"
            f"• User: @{sender_username}\n"
            f"• Amount: ₹{amt}\n"
            f"• UPI ID: `{upi_id}`\n\n"
            f"Admin verify karke transfer bhej denge! ✅"
        )
        sent = await update.message.reply_text(msg, parse_mode="Markdown")
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
        return

    # 9. LUDO KING ROOM CODE
    code_match = re.search(r"\b\d{8}\b", text)
    if code_match or clean_cmd.startswith("code "):
        code_val = code_match.group(0) if code_match else clean_cmd.replace("code", "").strip()
        c.execute("SELECT * FROM games WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (sender_clean, sender_clean))
        game = c.fetchone()
        if game:
            sent_code = await update.message.reply_text(
                f"🎮 **LUDO ROOM CODE:** `{code_val}`\n\nPlayers: @{game['host']} VS @{game['opponent']}\nMatch start karein! 🎲",
                parse_mode="Markdown"
            )
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
            return

    # 10. REPLY TO FIX MATCH WITH INLINE BUTTONS (CANCEL, #1 WON, #2 WON)
    positive_replies = [
        "ok", "okay", "lga", "lagao", "laga do", "play", "done", "khelna", 
        "khelo", "ao", "aao", "yes", "set", "ha", "haa", "accept", "match", 
        "deal", "aaja", "aajao", "bhejo", "dal", "daal", "confirm", "ready"
    ]
    is_positive_reply = any(clean_cmd == p or clean_cmd.startswith(p + " ") or clean_cmd.endswith(" " + p) for p in positive_replies)

    if update.message.reply_to_message and is_positive_reply:
        replied_msg = update.message.reply_to_message
        replied_user = replied_msg.from_user
        if not replied_user:
            return

        host_uname = replied_user.username or replied_user.first_name
        host_name = replied_user.first_name or host_uname
        opp_uname = sender_username
        opp_name = sender_name

        if host_uname.lower() == opp_uname.lower():
            return

        amt = parse_amount(replied_msg.text or "")
        if not amt:
            return

        mode_detected = detect_mode(replied_msg.text or "")

        host_rec = get_user_data(host_uname, host_name)
        opp_rec = get_user_data(opp_uname, opp_name)

        host_old_bal = float(host_rec["balance"])
        opp_old_bal = float(opp_rec["balance"])

        host_new_bal = host_old_bal - amt
        opp_new_bal = opp_old_bal - amt

        host_dot = "🟢" if host_new_bal >= 0 else "🔴"
        opp_dot = "🟢" if opp_new_bal >= 0 else "🔴"

        update_user_balance(host_uname, host_new_bal)
        update_user_balance(opp_uname, opp_new_bal)

        table_num = get_next_counter("table_counter")

        # Database me game save taaki buttons kaam karein
        c.execute("INSERT INTO games (table_no, host, opponent, amount, mode, status) VALUES (?, ?, ?, ?, ?, 'PLAYING')", 
                  (table_num, host_uname, opp_uname, amt, mode_detected))
        game_id = c.lastrowid
        c.execute("UPDATE users SET in_match = 1 WHERE username IN (?, ?)", (host_uname.lower(), opp_uname.lower()))
        db.commit()

        # EXACT INLINE BUTTONS (Cancel, Winner 1, Winner 2)
        inline_kb = [
            [InlineKeyboardButton("🚫 Cancel This Table", callback_data=f"cancel:{game_id}")],
            [
                InlineKeyboardButton(f"🏆 #1 Won ({host_name[:8]})", callback_data=f"win1:{game_id}"),
                InlineKeyboardButton(f"🏆 #2 Won ({opp_name[:8]})", callback_data=f"win2:{game_id}")
            ]
        ]
        keyboard = InlineKeyboardMarkup(inline_kb)

        # EXACT CARD FORMAT
        msg = (
            f"🎲 **Table No. {table_num}**\n\n"
            f"(1). {host_name} ✅✅\n\n"
            f"(2). {opp_name}\n\n"
            f"{int(amt)} ✅ {mode_detected}\n\n"
            f"{host_dot} {host_name} estimate:\n"
            f"{host_old_bal:.1f} - {amt:.1f} ➔ {host_new_bal:.1f}\n\n"
            f"{opp_dot} {opp_name} estimate:\n"
            f"{opp_old_bal:.1f} - {amt:.1f} ➔ {opp_new_bal:.1f}"
        )

        if LAST_ACTIVE_TABLE_MSG_ID:
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, LAST_ACTIVE_TABLE_MSG_ID, 30))

        sent_table = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        LAST_ACTIVE_TABLE_MSG_ID = sent_table.message_id

        # 30 SECONDS BAAD PURGE: Host bet & Opponent OK
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, replied_msg.message_id, 30))
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))

        if host_clean := (replied_user.username or "").lower().replace("@", ""):
            USER_LAST_BET_MSG.pop(host_clean, None)

        await sync_pinned_sheet(update.effective_chat.id, context)
        return

    # 11. SILENT BET WITH 30 SECONDS AUTO PURGE
    bet_pattern = re.search(r"\b(\d+(?:\.\d+)?)\s*(k)?\s*(full|classic|timer|quick|fast|speed|t|ff|f)?\b", text)
    if bet_pattern:
        amt = parse_amount(text)
        if amt and amt >= 10.0:
            if old_mid := USER_LAST_BET_MSG.get(sender_clean):
                asyncio.create_task(safe_delete(context, update.effective_chat.id, old_mid))
            USER_LAST_BET_MSG[sender_clean] = update.message.message_id
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
            return

    return

# Global Error Handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception while handling update:", exc_info=context.error)

# ---------------- MAIN FUNCTION ----------------
def main():
    Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(table_action_callback))
    app.add_handler(MessageHandler(filters.TEXT, zero_slash_table_power))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_messages))

    app.add_error_handler(error_handler)

    logging.info("Sky Table Powar with Interactive Buttons Active...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
