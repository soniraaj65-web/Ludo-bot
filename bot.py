import os
import re
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

BAD_WORDS = [
    "mc", "bc", "bhosdike", "chutiya", "madarchod", "gandu", 
    "lauda", "lodu", "behenchod", "harami", "bkl", "bsdk", "randi",
    "chudai", "madarjat", "bhen ke lode"
]

logging.basicConfig(level=logging.INFO)

# ---------------- DUMMY HTTP SERVER (RENDER KEEP-ALIVE) ----------------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Sky Table Powar Live Engine!")

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
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k", text)
    if k_match:
        return float(k_match.group(1)) * 1000.0
    num_match = re.search(r"\b(\d+)\b", text)
    if num_match:
        return float(num_match.group(1))
    return None

# ---------------- PINNED SHEET GENERATOR & SYNC ----------------
def generate_sheet_text():
    c.execute("SELECT name, username, balance FROM users WHERE balance > 0 ORDER BY balance DESC")
    rows = c.fetchall()
    
    total_balance = sum(r["balance"] for r in rows)
    
    text = "📊 **SKY KING CLUB • LIVE BALANCE SHEET** 📊\n"
    text += "──────────────────────────────\n"
    
    if not rows:
        text += "• _Filhal sabhi accounts 0.0 par hain._\n"
    else:
        for idx, r in enumerate(rows, start=1):
            disp_name = r["name"] or r["username"]
            text += f"`{idx:02d}.` **{disp_name}** (`@{r['username']}`): **₹{r['balance']:.1f}**\n"
            
    text += "──────────────────────────────\n"
    text += f"💰 **Total Club Balance:** ₹{total_balance:.1f}\n"
    text += "🔄 _Yeh list real-time auto update hoti hai._"
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

# ---------------- WELCOME HANDLER ----------------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.old_chat_member.status in ["left", "kicked"] and result.new_chat_member.status in ["member", "administrator"]:
        new_user = result.new_chat_member.user
        mention = f"@{new_user.username}" if new_user.username else new_user.first_name
        
        welcome_text = (
            f"👋 *WELCOME TO SKY KING LUDO CLUB, {mention}!* 🎲\n\n"
            "✨ *Direct table lagane ke liye likhein:*\n"
            "👉 `50` | `100` | `500 full` | `50 t` | `1k` | `5kff`\n\n"
            "• Challenge par reply karke `ok` ya `lga` karein (Match Fix & Pay)\n"
            "• Info dekhne ke liye: `info`\n"
            "• Deposit ke liye: `qr`"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, parse_mode="Markdown")

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

# ---------------- MAIN ZERO-SLASH PROCESSING ENGINE ----------------
async def zero_slash_table_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_LOCKED, ACTION_COUNTER, PINNED_SHEET_MSG_ID
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
            await update.message.reply_text("📌 *Balance Sheet successfully pinned! Ab yeh automatic live update hoti rahegi.*", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Pin message error: {e}")
            await update.message.reply_text("⚠️ Bot ko 'Pin Messages' ki admin permission check karein!")
        return

    # 2. LOCK / UNLOCK SYSTEM (Admin)
    if clean_cmd in ["lock", "close", "band"]:
        if sender_clean in ADMINS:
            GROUP_LOCKED = True
            await update.message.reply_text("🔒 *TABLE LOCK HO GAYI HAI!* Naye matches lagana band hai.", parse_mode="Markdown")
            return
    elif clean_cmd in ["unlock", "open group", "chalu", "start"]:
        if sender_clean in ADMINS:
            GROUP_LOCKED = False
            await update.message.reply_text("🔓 *TABLE OPEN HO GAYI HAI!* Khelna shuru kar sakte hain.", parse_mode="Markdown")
            return

    # 3. ANTI-GALI & ANTI-LINK FILTER (Admins Bypassed)
    if sender_clean not in ADMINS:
        words = text.split()
        if any(bad in words or bad in text for bad in BAD_WORDS):
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⚠️ {sender_name}, abusive bhasha delete kar di gayi hai!"
                )
            except Exception as e:
                logging.error(f"Moderation error: {e}")
            return

        if "http://" in text or "https://" in text or "t.me/" in text:
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⚠️ {sender_name}, promotional links allowed nahi hain!"
                )
            except Exception as e:
                logging.error(f"Link deletion error: {e}")
            return

    # 4. ADMIN REPLY BALANCE ADD (e.g. "add 1k", "+1000", "ubdet 1k", "add 50")
    add_match = re.match(r"^(?:/)?(?:add|addbal|\+|ubdet|update bal|update)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
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

    # 5. ADMIN REPLY BALANCE CUT (e.g. "cut 500", "-500", "cut 50")
    cut_match = re.match(r"^(?:/)?(?:cut|cutbal|-)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
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

    # 6. USER INFO CARD (e.g. "info", "bal")
    if clean_cmd in ["info", "bal", "balance", "mybal", "profile", "passbook"]:
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

    # 7. DIRECT QR & PAYMENT TRIGGERS
    if clean_cmd in ["qr", "payment", "scanner", "pay", "upi", "paisa"]:
        await send_qr_message(update.effective_chat.id, context, update.message.message_id)
        return

    # 8. CANCEL OPEN CHALLENGE
    if clean_cmd in ["cancel", "delete", "hatao", "back"]:
        c.execute("SELECT id FROM games WHERE host = ? AND status = 'OPEN'", (sender_clean,))
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM games WHERE id = ?", (row["id"],))
            db.commit()
            await update.message.reply_text(f"✅ @{sender_clean}, open challenge cancel kar diya gaya.")
        return

    # 9. DIRECT WITHDRAWAL (e.g. "wd 500 upi@id" / "withdraw 100 name@okaxis")
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

    # 10. LUDO KING ROOM CODE DETECTION (8-digit number)
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

    # 11. REPLY TO ACCEPT & FIX MATCH ("ok", "lga", "lagao", "play", "done")
    accept_keywords = ["ok", "lga", "lagao", "done", "play", "khelna", "ao", "aao", "yes", "set", "khelo"]
    if update.message.reply_to_message and clean_cmd in accept_keywords:
        if GROUP_LOCKED:
            await update.message.reply_text("🔒 Group currently locked hai.")
            return

        replied_user = update.message.reply_to_message.from_user
        if not replied_user:
            return

        host_uname = replied_user.username or replied_user.first_name
        host_name = replied_user.first_name or host_uname
        opp_uname = sender_username
        opp_name = sender_name

        if host_uname.lower() == opp_uname.lower():
            await update.message.reply_text("❌ Khud ke challenge par match fix nahi kar sakte.")
            return

        amt = parse_amount(update.message.reply_to_message.text or "") or 50.0

        host_rec = get_user_data(host_uname, host_name)
        opp_rec = get_user_data(opp_uname, opp_name)

        ACTION_COUNTER += 1
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Estimate", callback_data="none")]])

        msg = (
            f"@{host_uname} @{opp_uname}\n"
            f"{int(amt)}✅\n\n"
            f"**Action #{ACTION_COUNTER} successful! ✅**\n\n"
            f"🔴 **{host_name} estimate:**\n"
            f"{host_rec['balance']} - {amt} ➔ {host_rec['balance'] - amt}\n\n"
            f"🟢 **{opp_name} estimate:**\n"
            f"{opp_rec['balance']} - {amt} ➔ {opp_rec['balance'] - amt}"
        )

        c.execute("INSERT INTO games (host, opponent, amount, status) VALUES (?, ?, ?, 'PLAYING')", (host_uname, opp_uname, amt))
        c.execute("UPDATE users SET in_match = 1 WHERE username IN (?, ?)", (host_uname.lower(), opp_uname.lower()))
        db.commit()

        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
        return

    # 12. WINNER RESULT VIA REPLY ("win", "winner", "ss")
    if update.message.reply_to_message and clean_cmd in ["win", "winner", "ss", "loss"] and sender_clean in ADMINS:
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

    # 13. UNIVERSAL NATURAL MARKET CHALLENGE HIT ENGINE
    # Matches: 50, 100, 500, 500 full, 50 t, 1k, 5kff, 2k quick, 5k full 500+++, etc.
    bet_pattern = re.search(r"\b(\d+(?:\.\d+)?)\s*(k)?\s*(full|classic|timer|quick|fast|t|ff|f)?\b", text)
    if bet_pattern:
        val = float(bet_pattern.group(1))
        is_k = bet_pattern.group(2)
        tag = (bet_pattern.group(3) or "").lower()

        amt = val * 1000.0 if is_k else val

        if amt >= 10.0:
            if GROUP_LOCKED:
                await update.message.reply_text("🔒 Group currently locked hai.")
                return

            mode = "TIMER" if tag in ["t", "timer", "quick", "fast"] else "FULL"

            c.execute("INSERT INTO games (host, amount, mode, status) VALUES (?, ?, ?, 'OPEN')", (sender_clean, amt, mode))
            db.commit()

            await update.message.reply_text(
                f"🎲 **TABLE OPENED ({mode})**\n\n"
                f"👤 Host: @{sender_clean}\n"
                f"💰 Amount: **₹{int(amt) if amt.is_integer() else amt}**\n\n"
                f"👉 Khelne ke liye reply karein: `ok` ya `lga`"
            )
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

    logging.info("Zero-Slash Engine with Pinned Sheet Active...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
