import os
import re
import asyncio
import sqlite3
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
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

GROUP_LOCKED = False
ACTION_COUNTER = 90
PINNED_SHEET_MSG_ID = None

# Track last open message ID per user: {username: message_id}
USER_LAST_BET_MSG = {}

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
        self.wfile.write(b"Sky Table Powar Ultimate Engine Live!")

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
    host TEXT,
    opponent TEXT,
    amount REAL,
    mode TEXT DEFAULT 'CLASSIC',
    status TEXT
)
""")
db.commit()

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

async def safe_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

# ---------------- PINNED SHEET GENERATOR & LIVE SYNC ----------------
def generate_sheet_text():
    c.execute("SELECT name, username, balance FROM users WHERE balance > 0 ORDER BY balance DESC")
    rows = c.fetchall()
    total_balance = sum(r["balance"] for r in rows)
    
    text = "📊 **THE LUDO EMPIRE • LIVE BALANCE SHEET** 📊\n"
    text += "──────────────────────────────\n"
    if not rows:
        text += "• _Filhal sabhi accounts 0.0 par hain._\n"
    else:
        for idx, r in enumerate(rows, start=1):
            disp_name = r["name"] or r["username"]
            text += f"`{idx:02d}.` **{disp_name}** (`@{r['username']}`): **₹{r['balance']:.1f}**\n"
            
    text += "──────────────────────────────\n"
    text += f"💰 **Total Club Balance:** ₹{total_balance:.1f}\n"
    text += "🔄 _Yeh ledger real-time auto update hota hai._"
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
        f"💳 *PAYMENT QR DETAILS*\n\n"
        f"• *Name:* {PAYEE_NAME}\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        f"Payment karke screenshot chat me bhejein!"
    )
    if os.path.exists("qr.jpg"):
        with open("qr.jpg", "rb") as p:
            await context.bot.send_photo(chat_id=chat_id, photo=p, caption=caption, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    else:
        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_to_message_id=reply_to_id)

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
            "• Challenge par reply karke `ok` ya `lga` karein (Match Fix & Pay)\n"
            "• Info check karne ke liye: `info`\n"
            "• QR/Deposit ke liye: `qr`"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, parse_mode="Markdown")

# ---------------- COMPLETE ULTRA-RESPONSIVE ENGINE ----------------
async def zero_slash_table_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_LOCKED, ACTION_COUNTER, PINNED_SHEET_MSG_ID, USER_LAST_BET_MSG
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip()
    text = raw_text.lower()
    sender = update.effective_user
    sender_name = sender.first_name or "Player"
    sender_username = sender.username or sender_name
    sender_clean = (sender.username or "").lower().replace("@", "")

    clean_cmd = text.lstrip("/").strip()

    # 1. PIN SHEET / MASTER LEDGER TRIGGER
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
            await update.message.reply_text("📌 *Balance Sheet successfully pinned! Ab yeh real-time live update hoti rahegi.*", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Pin message error: {e}")
        return

    # 2. LOCK / UNLOCK SYSTEM
    if clean_cmd in ["lock", "close", "band"]:
        if sender_clean in ADMINS:
            GROUP_LOCKED = True
            await update.message.reply_text("🔒 *TABLE LOCK HO GAYI HAI!* Naye matches lagana band hai.", parse_mode="Markdown")
            return
    elif clean_cmd in ["unlock", "open group", "chalu", "start", "khula"]:
        if sender_clean in ADMINS:
            GROUP_LOCKED = False
            await update.message.reply_text("🔓 *TABLE OPEN HO GAYI HAI!* Khelna shuru kar sakte hain.", parse_mode="Markdown")
            return

    # 3. ANTI-GALI & ANTI-LINK FILTER (Instant Background Purge)
    if sender_clean not in ADMINS:
        words = text.split()
        if any(bad in words or bad in text for bad in BAD_WORDS) or ("http://" in text or "https://" in text or "t.me/" in text):
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
            return

    # 4. ADMIN REPLY BALANCE ADD (e.g. "add 1k", "+500", "ubdet 1k", "credit 1k")
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
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                await sync_pinned_sheet(update.effective_chat.id, context)
                return

    # 5. ADMIN REPLY BALANCE CUT (e.g. "cut 500", "-500", "debit 500", "kat 500")
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
                new_bal = max(0.0, old_bal - amt)
                update_user_balance(target_uname, new_bal, target_name)

                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Full Details", callback_data="none")]])
                msg = (
                    f"**Balance Deducted ✂️**\n\n"
                    f"💳 **New Balance:** {new_bal}\n"
                    f"👤 **User:** {target_name}\n\n"
                    f"_changes: {old_bal} - {amt}_"
                )
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                await sync_pinned_sheet(update.effective_chat.id, context)
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
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
        return

    # 7. QR CODE
    if clean_cmd in ["qr", "payment", "scanner", "pay", "upi", "paisa"]:
        await send_qr_message(update.effective_chat.id, context, update.message.message_id)
        return

    # 8. WITHDRAWAL
    wd_match = re.match(r"^(?:/)?(?:withdraw|wd|nikalo)\s+(\d+)\s+([a-zA-Z0-9.\-_+@]+)$", text)
    if wd_match:
        amt = float(wd_match.group(1))
        upi_id = wd_match.group(2)
        user_rec = get_user_data(sender_username, sender_name)
        if user_rec["balance"] < amt:
            await update.message.reply_text(f"❌ Low Balance! Aapka balance ₹{user_rec['balance']} hai.")
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
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # 9. LUDO KING ROOM CODE (8 DIGITS ANYWHERE)
    code_match = re.search(r"\b\d{8}\b", text)
    if code_match or clean_cmd.startswith("code "):
        code_val = code_match.group(0) if code_match else clean_cmd.replace("code", "").strip()
        c.execute("SELECT * FROM games WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (sender_clean, sender_clean))
        game = c.fetchone()
        if game:
            await update.message.reply_text(
                f"🎮 **LUDO ROOM CODE:** `{code_val}`\n\nPlayers: @{game['host']} VS @{game['opponent']}\nMatch start karein! 🎲",
                parse_mode="Markdown"
            )
            return

    # 10. EXPANDED POSITIVE REPLY KEYWORDS + STRICT BALANCE CHECK + DUAL PURGE
    positive_replies = [
        "ok", "okay", "lga", "lagao", "laga do", "play", "done", "khelna", 
        "khelo", "ao", "aao", "yes", "set", "ha", "haa", "accept", "match", 
        "deal", "aaja", "aajao", "bhejo", "dal", "daal", "confirm", "ready"
    ]
    is_positive_reply = any(clean_cmd == p or clean_cmd.startswith(p + " ") or clean_cmd.endswith(" " + p) for p in positive_replies)

    if update.message.reply_to_message and is_positive_reply:
        if GROUP_LOCKED:
            await update.message.reply_text("🔒 Group currently locked hai.")
            return

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

        host_rec = get_user_data(host_uname, host_name)
        opp_rec = get_user_data(opp_uname, opp_name)

        # STRICT BALANCE CHECK
        low_balance_users = []
        if host_rec["balance"] < amt:
            low_balance_users.append(f"@{host_uname} (₹{host_rec['balance']})")
        if opp_rec["balance"] < amt:
            low_balance_users.append(f"@{opp_uname} (₹{opp_rec['balance']})")

        if low_balance_users:
            low_str = " aur ".join(low_balance_users)
            await update.message.reply_text(
                f"❌ **Table nahi lag sakti!**\n\n{low_str} ke paas ₹{int(amt)} balance nahi hai.\n\nDeposit karne ke liye chat mein `qr` bhejein."
            )
            return

        # Deduct match entry balance
        update_user_balance(host_uname, host_rec["balance"] - amt)
        update_user_balance(opp_uname, opp_rec["balance"] - amt)

        ACTION_COUNTER += 1
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Estimate", callback_data="none")]])

        tag_host = f"@{host_uname}" if replied_user.username else host_name
        tag_opp = f"@{opp_uname}" if sender.username else opp_name

        msg = (
            f"{tag_host} {tag_opp}\n"
            f"{int(amt)}✅\n\n"
            f"Action #{ACTION_COUNTER} successful! ✅\n\n"
            f"🔴 {host_name} estimate:\n"
            f"{host_rec['balance']} - {amt} ➔ {host_rec['balance'] - amt}\n\n"
            f"🟢 {opp_name} estimate:\n"
            f"{opp_rec['balance']} - {amt} ➔ {opp_rec['balance'] - amt}"
        )

        c.execute("INSERT INTO games (host, opponent, amount, status) VALUES (?, ?, ?, 'PLAYING')", (host_uname, opp_uname, amt))
        c.execute("UPDATE users SET in_match = 1 WHERE username IN (?, ?)", (host_uname.lower(), opp_uname.lower()))
        db.commit()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            reply_markup=keyboard
        )

        # DUAL AUTO DELETE: Purana Bet Message + Opponent OK Message
        asyncio.create_task(safe_delete(context, update.effective_chat.id, replied_msg.message_id))
        asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))

        if host_clean := (replied_user.username or "").lower().replace("@", ""):
            USER_LAST_BET_MSG.pop(host_clean, None)

        await sync_pinned_sheet(update.effective_chat.id, context)
        return

    # 11. WINNER RESULT VIA REPLY
    if update.message.reply_to_message and clean_cmd in ["win", "winner", "ss", "pass", "loss"] and sender_clean in ADMINS:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_uname = replied_user.username or replied_user.first_name
            c.execute("SELECT * FROM games WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (target_uname, target_uname))
            game = c.fetchone()
            if game:
                tot_pot = game["amount"] * 2.0
                commission = tot_pot * (COMMISSION_PERCENT / 100.0)
                win_amt = tot_pot - commission

                user_rec = get_user_data(target_uname)
                new_bal = user_rec["balance"] + win_amt
                update_user_balance(target_uname, new_bal)

                c.execute("DELETE FROM games WHERE id = ?", (game["id"],))
                c.execute("UPDATE users SET in_match = 0 WHERE username IN (?, ?)", (game["host"], game["opponent"]))
                db.commit()

                await update.message.reply_text(
                    f"🏆 **WINNER CONFIRMED!**\n\n"
                    f"Winner: @{target_uname}\n"
                    f"Pot: ₹{tot_pot}\n"
                    f"Credited: **₹{win_amt}** (10% Commission Cut) ✅"
                )
                await sync_pinned_sheet(update.effective_chat.id, context)
                return

    # 12. SILENT BET WITH OLD MESSAGE PURGE
    # Matches: 50, 100, 500 full, 50 t, 1k, 5kff, 2k quick, 5k full 500+++, choda, etc.
    bet_pattern = re.search(r"\b(\d+(?:\.\d+)?)\s*(k)?\s*(full|classic|timer|quick|fast|speed|t|ff|f)?\b", text)
    if bet_pattern:
        amt = parse_amount(text)
        if amt and amt >= 10.0:
            if old_mid := USER_LAST_BET_MSG.get(sender_clean):
                asyncio.create_task(safe_delete(context, update.effective_chat.id, old_mid))
            USER_LAST_BET_MSG[sender_clean] = update.message.message_id
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
    app.add_handler(MessageHandler(filters.TEXT, zero_slash_table_power))
    app.add_handler(MessageHandler(filters.PHOTO, zero_slash_table_power))

    app.add_error_handler(error_handler)

    logging.info("Ultra-Clean Auto-Delete Engine Live & Polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
