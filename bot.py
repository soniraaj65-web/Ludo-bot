import os
import re
import asyncio
import sqlite3
import logging
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
USER_LAST_BET_MSG = {}
LAST_ACTIVE_TABLE_MSG_ID = None
LAST_ACTIVE_ESTIMATE_MSG_ID = None

logging.basicConfig(level=logging.INFO)

# ---------------- RENDER 24/7 DUMMY SERVER ----------------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Pure Ludo Match System Live!")

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    server.serve_forever()

# ---------------- DATABASE ENGINE ----------------
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
    username = str(username).lower().replace("@", "").strip()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT OR REPLACE INTO users (username, name, balance, side_balance, in_match) VALUES (?, ?, 0.0, 0.0, 0)", (username, fallback_name))
        db.commit()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = c.fetchone()
    return row

def update_user_balance(username, new_bal, name=None):
    username = str(username).lower().replace("@", "").strip()
    if name:
        c.execute("UPDATE users SET balance = ?, name = ? WHERE username = ?", (float(new_bal), name, username))
    else:
        c.execute("UPDATE users SET balance = ? WHERE username = ?", (float(new_bal), username))
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
    t_lower = text.lower()
    if any(k in t_lower for k in ["timer", "quick", "fast", "speed"]) or re.search(r"\b\d+\s*t\b", t_lower):
        return "Timer"
    return "Classic Full"

async def safe_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def delayed_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, delay_seconds=30):
    await asyncio.sleep(delay_seconds)
    await safe_delete(context, chat_id, message_id)

# ---------------- PINNED LEDGER SHEET ----------------
def generate_sheet_text():
    c.execute("SELECT name, username, balance FROM users WHERE balance != 0 ORDER BY balance DESC")
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) AS total_live FROM games WHERE status = 'PLAYING'")
    live_matches = c.fetchone()["total_live"]
    total_balance = sum(r["balance"] for r in rows)
    current_time = datetime.now().strftime("%I:%M %p")
    
    text = (
        "👑 𝐓𝐇𝐄 𝐋𝐔𝐃𝐎 𝐄𝐌𝐏𝐈𝐑𝐄 • 𝐋𝐈𝐕𝐄 𝐋𝐄𝐃𝐆𝐄𝐑 👑\n"
        "════════════════════════════\n"
        "📊 MEMBER BALANCES:\n"
        "────────────────────────────\n"
    )
    if not rows:
        text += "• Sabhi accounts filhal clear hain (₹0.0).\n"
    else:
        for idx, r in enumerate(rows, start=1):
            disp = f"@{r['username']}" if r['username'] else r['name']
            bal = r["balance"]
            dot = "🟢" if bal >= 0 else "🔴"
            text += f"{idx:02d}. {dot} {disp}: ₹{bal:.1f}\n"
            
    text += (
        "────────────────────────────\n"
        f"💰 Total Club Reserve : ₹{total_balance:.1f}\n"
        f"⚔️ Active Tables Live : {live_matches}\n"
        f"⏱️ Last Updated At    : {current_time}\n"
        "════════════════════════════\n"
        "🔄 Automated Real-Time Settlement Engine."
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
                text=sheet_content
            )
        except Exception:
            pass

# ---------------- INTERACTIVE BUTTON CALLBACKS ----------------
async def table_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_clean = (user.username or user.first_name or "").lower().replace("@", "")

    data = query.data.split(":")
    action = data[0]
    game_id = int(data[1])

    c.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    game = c.fetchone()
    if not game:
        await query.answer("⚠️ Match record not found!", show_alert=True)
        return

    table_no = game["table_no"]
    host = game["host"]
    opponent = game["opponent"]
    amt = float(game["amount"])
    est_msg_id = game["estimate_msg_id"]

    # Real-Time Estimate Button Check
    if action == "est":
        host_rec = get_user_data(host)
        opp_rec = get_user_data(opponent)
        await query.answer(
            f"📋 Action #{table_no} Current Balances:\n\n"
            f"@{host}: ₹{host_rec['balance']:.1f}\n"
            f"@{opponent}: ₹{opp_rec['balance']:.1f}",
            show_alert=True
        )
        return

    # Admin check
    is_admin = False
    try:
        cm = await context.bot.get_chat_member(query.message.chat_id, user.id)
        is_admin = (user_clean in ADMINS) or (cm.status in ["administrator", "creator"])
    except Exception:
        is_admin = user_clean in ADMINS

    if not is_admin:
        await query.answer("❌ Only Admins can settle or cancel matches!", show_alert=True)
        return

    if game["status"] != "PLAYING":
        await query.answer("⚠️ Match already closed!", show_alert=True)
        return

    # 1. CANCEL & REFUND (REAL-TIME EDIT IN SETTLEMENT LOG)
    if action == "cancel":
        host_rec = get_user_data(host)
        opp_rec = get_user_data(opponent)

        new_host_bal = host_rec["balance"] + amt
        new_opp_bal = opp_rec["balance"] + amt

        update_user_balance(host, new_host_bal)
        update_user_balance(opponent, new_opp_bal)

        c.execute("UPDATE games SET status = 'CANCELED' WHERE id = ?", (game_id,))
        c.execute("UPDATE users SET in_match = 0 WHERE username IN (?, ?)", (host.lower(), opponent.lower()))
        db.commit()

        # Table buttons remove
        await query.edit_message_reply_markup(reply_markup=None)

        # Real-Time Settlement Card Edit
        if est_msg_id:
            try:
                updated_est_card = (
                    f"📋 ACTION #{table_no} SETTLEMENT LOG 🚫 [CANCELED]\n"
                    f"──────────────────────\n"
                    f"🟢 @{host}:\n"
                    f"Refund: +₹{amt:.1f} ➔ ₹{new_host_bal:.1f}\n\n"
                    f"🟢 @{opponent}:\n"
                    f"Refund: +₹{amt:.1f} ➔ ₹{new_opp_bal:.1f}\n"
                    f"──────────────────────"
                )
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=est_msg_id,
                    text=updated_est_card,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Real-Time Estimate", callback_data=f"est:{game_id}")]])
                )
            except Exception as e:
                logging.error(f"Error editing estimate card: {e}")

        cancel_msg = await query.message.reply_text(
            f"🚫 MATCH #{table_no} CANCELED!\n"
            f"Dono players (@{host} & @{opponent}) ko ₹{amt:.1f} refund kar diya gaya hai."
        )
        await sync_pinned_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, cancel_msg.message_id, 30))
        await query.answer("Match Canceled & Refunded!")
        return

    # 2. WINNER DECLARATION (REAL-TIME EDIT IN SETTLEMENT LOG)
    if action in ["win1", "win2"]:
        winner_uname = host if action == "win1" else opponent
        loser_uname = opponent if action == "win1" else host

        tot_pot = amt * 2.0
        commission = tot_pot * (COMMISSION_PERCENT / 100.0)
        win_amt = tot_pot - commission

        winner_rec = get_user_data(winner_uname)
        loser_rec = get_user_data(loser_uname)

        new_winner_bal = winner_rec["balance"] + win_amt
        update_user_balance(winner_uname, new_winner_bal)

        c.execute("UPDATE games SET status = 'FINISHED' WHERE id = ?", (game_id,))
        c.execute("UPDATE users SET in_match = 0 WHERE username IN (?, ?)", (host.lower(), opponent.lower()))
        db.commit()

        await query.edit_message_reply_markup(reply_markup=None)

        # Real-Time Settlement Card Edit
        if est_msg_id:
            try:
                updated_est_card = (
                    f"📋 ACTION #{table_no} SETTLEMENT LOG ✅ [SETTLED]\n"
                    f"──────────────────────\n"
                    f"👑 Winner: @{winner_uname}\n"
                    f"+₹{win_amt:.1f} ({COMMISSION_PERCENT}% Cut) ➔ New Bal: ₹{new_winner_bal:.1f}\n\n"
                    f"👤 Opponent: @{loser_uname}\n"
                    f"Current Balance: ₹{loser_rec['balance']:.1f}\n"
                    f"──────────────────────"
                )
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=est_msg_id,
                    text=updated_est_card,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Real-Time Estimate", callback_data=f"est:{game_id}")]])
                )
            except Exception as e:
                logging.error(f"Error editing estimate card: {e}")

        win_msg = await query.message.reply_text(
            f"🏆 MATCH #{table_no} WINNER CONFIRMED! 🏆\n\n"
            f"👑 Winner: @{winner_uname}\n"
            f"💰 Total Pot: ₹{tot_pot:.1f}\n"
            f"✅ Credited: ₹{win_amt:.1f} ({COMMISSION_PERCENT}% Cut)"
        )
        await sync_pinned_sheet(query.message.chat_id, context)
        asyncio.create_task(delayed_delete(context, query.message.chat_id, win_msg.message_id, 30))
        await query.answer(f"@{winner_uname} won!")
        return

# ---------------- MATCH ENGINE ----------------
async def main_match_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PINNED_SHEET_MSG_ID, USER_LAST_BET_MSG, LAST_ACTIVE_TABLE_MSG_ID, LAST_ACTIVE_ESTIMATE_MSG_ID
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip()
    text = raw_text.lower()
    sender = update.effective_user
    sender_name = sender.first_name or "Player"
    sender_username = sender.username or sender_name
    sender_clean = (sender.username or sender_name).lower().replace("@", "")

    # Admin check
    is_admin = False
    try:
        cm = await context.bot.get_chat_member(update.effective_chat.id, sender.id)
        is_admin = (sender_clean in ADMINS) or (cm.status in ["administrator", "creator"])
    except Exception:
        is_admin = sender_clean in ADMINS

    clean_cmd = text.lstrip("/").strip()

    # 1. PIN SHEET
    if clean_cmd in ["pinsheet", "sheet", "ledger"] and is_admin:
        sheet_text = generate_sheet_text()
        sent_msg = await update.message.reply_text(sheet_text)
        try:
            await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=sent_msg.message_id, disable_notification=True)
            PINNED_SHEET_MSG_ID = sent_msg.message_id
            asyncio.create_task(safe_delete(context, update.effective_chat.id, update.message.message_id))
        except Exception:
            pass
        return

    # 2. BALANCE ADD (Reply: 'add 500', '+1000')
    add_match = re.match(r"^(?:add|addbal|\+|credit)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and add_match and is_admin:
        target = update.message.reply_to_message.from_user
        if target:
            t_uname = target.username or target.first_name
            t_name = f"@{target.username}" if target.username else target.first_name
            amt = parse_amount(add_match.group(1))
            if amt:
                user_rec = get_user_data(t_uname, t_name)
                new_bal = float(user_rec["balance"]) + amt
                update_user_balance(t_uname, new_bal, t_name)
                sent = await update.message.reply_text(f"💳 Balance Credited ✅\nUser: {t_name}\nUpdated Balance: ₹{new_bal:.1f}")
                await sync_pinned_sheet(update.effective_chat.id, context)
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
                return

    # 3. BALANCE CUT (Reply: 'cut 200', '-500')
    cut_match = re.match(r"^(?:cut|cutbal|-|debit)\s*(\d+(?:\.\d+)?\s*k|\d+)", text)
    if update.message.reply_to_message and cut_match and is_admin:
        target = update.message.reply_to_message.from_user
        if target:
            t_uname = target.username or target.first_name
            t_name = f"@{target.username}" if target.username else target.first_name
            amt = parse_amount(cut_match.group(1))
            if amt:
                user_rec = get_user_data(t_uname, t_name)
                new_bal = float(user_rec["balance"]) - amt
                update_user_balance(t_uname, new_bal, t_name)
                sent = await update.message.reply_text(f"✂️ Balance Deducted\nUser: {t_name}\nUpdated Balance: ₹{new_bal:.1f}")
                await sync_pinned_sheet(update.effective_chat.id, context)
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 30))
                return

    # 4. USER BALANCE CHECK
    if clean_cmd in ["info", "bal", "balance", "mybal"]:
        user_rec = get_user_data(sender_username, sender_name)
        disp_u = f"@{sender.username}" if sender.username else sender_name
        sent = await update.message.reply_text(f"👤 {disp_u}\n💰 Balance: ₹{user_rec['balance']:.1f}")
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent.message_id, 20))
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 20))
        return

    # 5. ROOM CODE DETECTION
    code_match = re.search(r"\b\d{8}\b", text)
    if code_match or clean_cmd.startswith("code "):
        code_val = code_match.group(0) if code_match else clean_cmd.replace("code", "").strip()
        c.execute("SELECT * FROM games WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (sender_clean, sender_clean))
        game = c.fetchone()
        if game:
            await update.message.reply_text(
                f"🎲 𝐋𝐔𝐃𝐎 𝐑𝐎𝐎𝐌 𝐂𝐎𝐃𝐄: `{code_val}`\n\n"
                f"⚔️ Match #{game['table_no']} (@{game['host']} VS @{game['opponent']})\n"
                f"Room code enter karke match shuru karein!",
                parse_mode="Markdown"
            )
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
            return

    # 6. TABLE CREATION & THRESHOLD BALANCE CHECK
    if update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        amt = parse_amount(replied_msg.text or "")
        
        accept_triggers = {
            "t", "l", "k", "y", "h", "ok", "okay", "lga", "lagao", "lagado", 
            "lagade", "play", "done", "yes", "yup", "yo", "ha", "haa", "han", 
            "haan", "hm", "hmm", "hmmm", "accept", "ao", "aao", "aaja", "aajao", 
            "khelo", "khelna", "khel", "ready", "set", "deal", "confirm", "bhejo", "dal", "daal"
        }
        words = set(re.findall(r"\b\w+\b", text))
        is_positive = bool(words.intersection(accept_triggers)) or (text.strip() in accept_triggers)

        if amt and amt >= 10.0 and is_positive:
            host_user = replied_msg.from_user
            if not host_user:
                return

            host_uname = host_user.username or host_user.first_name
            host_name = host_user.first_name or host_uname
            opp_uname = sender_username
            opp_name = sender_name

            host_disp = f"@{host_user.username}" if host_user.username else host_name
            opp_disp = f"@{sender.username}" if sender.username else opp_name

            mode = detect_mode(replied_msg.text or "")

            host_rec = get_user_data(host_uname, host_name)
            opp_rec = get_user_data(opp_uname, opp_name)

            host_old = float(host_rec["balance"])
            opp_old = float(opp_rec["balance"])
            host_new = host_old - amt
            opp_new = opp_old - amt

            # THRESHOLD LIMIT CHECK (Agar balance amount se kam ho)
            if host_old < amt or opp_old < amt:
                failed_user = host_disp if host_old < amt else opp_disp
                fail_msg = (
                    f"⚠️ 𝐓𝐀𝐁𝐋𝐄 𝐂𝐀𝐍𝐍𝐎𝐓 𝐁𝐄 𝐂𝐑𝐄𝐀𝐓𝐄𝐃!\n\n"
                    f"Insufficient funds: {failed_user} ka balance required stake (₹{amt:.1f}) se kam hai.\n\n"
                    f"{'🟢' if host_old >= amt else '🔴'} {host_disp}: ₹{host_old:.1f}\n"
                    f"{'🟢' if opp_old >= amt else '🔴'} {opp_disp}: ₹{opp_old:.1f}"
                )
                sent_fail = await update.message.reply_text(fail_msg)
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, sent_fail.message_id, 20))
                return

            # Balances Deduct
            update_user_balance(host_uname, host_new)
            update_user_balance(opp_uname, opp_new)

            table_num = get_next_counter("table_counter")

            c.execute("INSERT INTO games (table_no, host, opponent, amount, mode, status, estimate_msg_id, chat_id) VALUES (?, ?, ?, ?, ?, 'PLAYING', NULL, ?)",
                      (table_num, host_uname, opp_uname, amt, mode, update.effective_chat.id))
            game_id = c.lastrowid
            c.execute("UPDATE users SET in_match = 1 WHERE username IN (?, ?)", (host_uname.lower(), opp_uname.lower()))
            db.commit()

            btn_h = host_disp[:12]
            btn_o = opp_disp[:12]

            # CARD 1: EXACT ROYAL BRAND TABLE ACTION CARD (Screenshot Format)
            table_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 CANCEL & REFUND", callback_data=f"cancel:{game_id}")],
                [
                    InlineKeyboardButton(f"👑 {btn_h} WON", callback_data=f"win1:{game_id}"),
                    InlineKeyboardButton(f"👑 {btn_o} WON", callback_data=f"win2:{game_id}")
                ]
            ])
            table_card = (
                f"⚔️ THE LUDO EMPIRE • MATCH #{table_num} ⚔️\n"
                f"──────────────────────\n"
                f"👤 Player 1: {host_disp}\n"
                f"👤 Player 2: {opp_disp}\n\n"
                f"💰 Stake: ₹{int(amt)} | Mode: {mode}\n"
                f"⚡ Match Status: LIVE IN PROGRESS 🎲\n"
                f"──────────────────────"
            )

            # CARD 2: EXACT REAL-TIME ESTIMATE SETTLEMENT LOG (Screenshot Format)
            h_dot = "🟢" if host_new >= 0 else "🔴"
            o_dot = "🟢" if opp_new >= 0 else "🔴"
            est_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Real-Time Estimate", callback_data=f"est:{game_id}")]])
            est_card = (
                f"📋 ACTION #{table_num} SETTLEMENT LOG ✅\n"
                f"──────────────────────\n"
                f"{h_dot} {host_disp}:\n"
                f"₹{host_old:.1f} - ₹{amt:.1f} ➔ ₹{host_new:.1f}\n\n"
                f"{o_dot} {opp_disp}:\n"
                f"₹{opp_old:.1f} - ₹{amt:.1f} ➔ ₹{opp_new:.1f}\n"
                f"──────────────────────"
            )

            # Purani Table & Estimate Delete
            if LAST_ACTIVE_TABLE_MSG_ID:
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, LAST_ACTIVE_TABLE_MSG_ID, 30))
            if LAST_ACTIVE_ESTIMATE_MSG_ID:
                asyncio.create_task(delayed_delete(context, update.effective_chat.id, LAST_ACTIVE_ESTIMATE_MSG_ID, 30))

            sent_t = await context.bot.send_message(chat_id=update.effective_chat.id, text=table_card, reply_markup=table_kb)
            LAST_ACTIVE_TABLE_MSG_ID = sent_t.message_id

            sent_e = await context.bot.send_message(chat_id=update.effective_chat.id, text=est_card, reply_markup=est_kb)
            LAST_ACTIVE_ESTIMATE_MSG_ID = sent_e.message_id

            # Database me Estimate Message ID link karna (taaki Settlement ke waqt real time edit ho sake)
            c.execute("UPDATE games SET estimate_msg_id = ? WHERE id = ?", (sent_e.message_id, game_id))
            db.commit()

            # Challenge aur acceptance messages 30 sec me delete
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, replied_msg.message_id, 30))
            asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))

            if host_clean := (replied_user.username or "").lower().replace("@", ""):
                USER_LAST_BET_MSG.pop(host_clean, None)

            await sync_pinned_sheet(update.effective_chat.id, context)
            return

    # 7. SILENT BET DETECTOR
    amt_test = parse_amount(text)
    if amt_test and amt_test >= 10.0:
        if old_mid := USER_LAST_BET_MSG.get(sender_clean):
            asyncio.create_task(safe_delete(context, update.effective_chat.id, old_mid))
        USER_LAST_BET_MSG[sender_clean] = update.message.message_id
        asyncio.create_task(delayed_delete(context, update.effective_chat.id, update.message.message_id, 30))
        return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception in main engine:", exc_info=context.error)

# ---------------- MAIN APPLICATION ----------------
def main():
    Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(table_action_callback))
    app.add_handler(MessageHandler(filters.TEXT, main_match_router))
    app.add_error_handler(error_handler)

    logging.info("The Ludo Empire Royal Match Engine Online...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
