import os
import sqlite3
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
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

# Galiyon aur spam words ki list
BAD_WORDS = [
    "mc", "bc", "bhosdike", "chutiya", "madarchod", "gandu", 
    "lauda", "lodu", "behenchod", "harami", "bkl", "bsdk", "randi"
]

logging.basicConfig(level=logging.INFO)

# ---------------- DUMMY HTTP SERVER (RENDER KEEP-ALIVE) ----------------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Ludo Empire Bot is Running!")

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
    balance INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT,
    opponent TEXT,
    amount INTEGER,
    status TEXT
)
""")
db.commit()

def get_user_balance(username):
    username = username.lower().replace("@", "")
    c.execute("SELECT balance FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    return row["balance"] if row else 0

def set_user_balance(username, bal):
    username = username.lower().replace("@", "")
    c.execute("INSERT OR REPLACE INTO users (username, balance) VALUES (?, ?)", (username, bal))
    db.commit()

# ---------------- WELCOME HANDLER (NEW MEMBERS) ----------------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.old_chat_member.status in ["left", "kicked"] and result.new_chat_member.status in ["member", "administrator"]:
        new_user = result.new_chat_member.user
        mention = f"@{new_user.username}" if new_user.username else new_user.first_name
        
        welcome_text = (
            f"👋 *WELCOME TO LUDO EMPIRE, {mention}!* 🎲\n\n"
            "✨ *Yahan khele aur jeetein 100% safe & fast payouts ke sath!*\n\n"
            "🎮 *Quick Commands:*\n"
            "• `/bal` - Apna wallet balance check karein\n"
            "• `/open <amount>` - New challenge create karein\n"
            "• `/table` - Active matches dekhein\n"
            "• `/qr` - Deposit scan aur UPI ID paane ke liye\n"
            "• `/withdraw <amt> <upi>` - Payout lene ke liye\n"
            "• `/rules` - Game ke rules padhein\n\n"
            "💰 *Add balance karne ke liye chat mein `qr` bhejein!*"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, parse_mode="Markdown")

# ---------------- AUTO MODERATION & TEXT TRIGGERS ----------------
async def auto_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower().strip()
    sender = update.effective_user
    username = f"@{sender.username}" if sender.username else sender.first_name
    sender_clean = (sender.username or "").lower().replace("@", "")

    # 1. Text Triggers (Sabke liye execute hoga, chahe user ho ya admin)
    if text in ["qr", "payment", "scanner"]:
        await qr_command(update, context)
        return
    elif text in ["bet", "open"]:
        await update.message.reply_text("🎲 Table open karne ke liye command bhejein: `/open <amount>` (Example: `/open 50`)", parse_mode="Markdown")
        return

    # 2. Admins ko gaali/link filter bypass karne allow karein
    if sender_clean in ADMINS:
        return

    # 3. Moderation Filters
    words = text.split()
    contains_bad_word = any(bad in words or bad in text for bad in BAD_WORDS)
    contains_link = "http://" in text or "https://" in text or "t.me/" in text

    if contains_bad_word:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ {username}, group me gaali ya abusive bhasha allowed nahi hai! Message deleted."
            )
        except Exception as e:
            logging.error(f"Moderation error: {e}")
        return

    if contains_link:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ {username}, group me promotional links bhejna mana hai! Message deleted."
            )
        except Exception as e:
            logging.error(f"Link deletion error: {e}")
        return

# ---------------- BOT HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 *WELCOME TO THE LUDO EMPIRE BOT* 👑\n\n"
        "🎮 *Player Commands:*\n"
        "• `/open <amount>` - Challenge create karo\n"
        "• `/join @host` - Challenge accept karo\n"
        "• `/code <room_code>` - Ludo room code bhejo\n"
        "• `/table` - Active challenges dekho\n"
        "• `/cancel` - Apna open challenge cancel karo\n"
        "• `/bal` - Apna wallet balance check karo\n"
        "• `/withdraw <amt> <upi>` - Withdrawal request lagao\n"
        "• `/rules` - Game rules padho\n"
        "• `/qr` - Deposit scan aur UPI ID paane ke liye\n\n"
        "⚡ Send `qr` or `bet` anytime in chat."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📜 *LUDO RULES:*\n\n"
        "1. Table join hone ke 5 min ke andar room code bhejna zaroori hai.\n"
        "2. Win hone ke baad result screenshot admin ko bhejein.\n"
        "3. Game me kisi bhi tarah ki cheating/hacks ban karwayenge.\n"
        "4. Platform commission 10% automatically deduct hoga."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        f"💳 *DEPOSIT PAYMENT DETAILS*\n\n"
        f"• *Name:* {PAYEE_NAME}\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        f"Payment karne ke baad screenshot admin ko bhejein balance add karwane ke liye!"
    )
    if os.path.exists("qr.jpg"):
        with open("qr.jpg", "rb") as p:
            await update.message.reply_photo(photo=p, caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.username
    if not sender:
        await update.message.reply_text("❌ Kripya Telegram par pehle apna username set karein.")
        return
    bal = get_user_balance(sender)
    await update.message.reply_text(f"💰 @{sender}, aapka balance: *₹{bal}*", parse_mode="Markdown")

async def open_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sender = update.effective_user.username
        if not sender:
            await update.message.reply_text("❌ Pehle apna Telegram username set karein.")
            return

        sender = sender.lower().replace("@", "")

        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("⚠️ Sahi format: `/open <amount>` (Example: `/open 50`)", parse_mode="Markdown")
            return

        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Amount 0 se zyada hona chahiye.")
            return

        bal = get_user_balance(sender)
        if bal < amount:
            await update.message.reply_text(f"❌ Low Balance! Aapka balance ₹{bal} hai. Deposit ke liye `/qr` use karein.")
            return

        c.execute("SELECT id FROM games WHERE host = ? AND status = 'OPEN'", (sender,))
        if c.fetchone():
            await update.message.reply_text("❌ Aapka ek match pehle se open hai! Pehle use `/cancel` karein.")
            return

        c.execute("INSERT INTO games (host, amount, status) VALUES (?, ?, 'OPEN')", (sender, amount))
        db.commit()

        await update.message.reply_text(
            f"🎲 *TABLE OPENED*\n\nHost: @{sender}\nAmount: *₹{amount}*\n\nJoin karne ke liye: `/join @{sender}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error in open_table: {e}")
        await update.message.reply_text("⚠️ Match create karte waqt error aaya.")

async def cancel_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.username
    if not sender:
        return
    sender = sender.lower().replace("@", "")
    c.execute("SELECT id FROM games WHERE host = ? AND status = 'OPEN'", (sender,))
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM games WHERE id = ?", (row["id"],))
        db.commit()
        await update.message.reply_text(f"✅ @{sender}, aapka open challenge cancel kar diya gaya hai.")
    else:
        await update.message.reply_text("❌ Aapka koi open challenge nahi mila.")

async def join_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sender = update.effective_user.username
        if not sender:
            await update.message.reply_text("❌ Pehle apna Telegram username set karein.")
            return

        sender = sender.lower().replace("@", "")

        if not context.args:
            await update.message.reply_text("⚠️ Sahi format: `/join @host_username`", parse_mode="Markdown")
            return

        host = context.args[0].lower().replace("@", "")

        if host == sender:
            await update.message.reply_text("❌ Aap apna khud ka match join nahi kar sakte.")
            return

        c.execute("SELECT * FROM games WHERE host = ? AND status = 'OPEN'", (host,))
        game = c.fetchone()

        if not game:
            await update.message.reply_text("❌ Yeh table exist nahi karti ya match start ho chuka hai.")
            return

        amt = game["amount"]
        if get_user_balance(sender) < amt:
            await update.message.reply_text(f"❌ Low balance! Is table ke liye ₹{amt} balance chahiye.")
            return

        if get_user_balance(host) < amt:
            await update.message.reply_text("❌ Host ke wallet me sufficient balance nahi hai.")
            return

        set_user_balance(host, get_user_balance(host) - amt)
        set_user_balance(sender, get_user_balance(sender) - amt)

        c.execute("UPDATE games SET opponent = ?, status = 'PLAYING' WHERE id = ?", (sender, game["id"]))
        db.commit()

        msg = (
            f"⚔️ *MATCH STARTED!*\n\n"
            f"Host: @{host}\n"
            f"Opponent: @{sender}\n"
            f"Amount: ₹{amt} each (Total Pot: ₹{amt * 2})\n\n"
            f"Host @{host}, please create Ludo King room and send: `/code <room_code>`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in join_table: {e}")
        await update.message.reply_text("⚠️ Join karte waqt error aaya.")

async def send_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.username
    if not sender or not context.args:
        await update.message.reply_text("⚠️ Sahi format: `/code <room_code>`")
        return

    sender = sender.lower().replace("@", "")
    code = context.args[0]

    c.execute("SELECT * FROM games WHERE host = ? AND status = 'PLAYING'", (sender,))
    game = c.fetchone()
    if game:
        await update.message.reply_text(
            f"🎮 *LUDO ROOM CODE:*\n`{code}`\n\nPlayers: @{game['host']} VS @{game['opponent']}\nEnjoy the match!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Aapka koi running match nahi mila.")

async def view_tables(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c.execute("SELECT * FROM games WHERE status = 'OPEN'")
    rows = c.fetchall()
    if not rows:
        await update.message.reply_text("📋 Abhi koi open table nahi hai. Naya create karne ke liye `/open <amount>` likhein.")
        return

    text = "📋 *ACTIVE TABLES:*\n\n"
    for r in rows:
        text += f"• Host: @{r['host']} | Entry: ₹{r['amount']} ➔ `/join @{r['host']}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ---------------- WITHDRAWAL SYSTEM ----------------

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sender = update.effective_user.username
        if not sender:
            await update.message.reply_text("❌ Pehle apna Telegram username set karein.")
            return

        sender_clean = sender.lower().replace("@", "")

        if len(context.args) < 2 or not context.args[0].isdigit():
            await update.message.reply_text("⚠️ Sahi format: `/withdraw <amount> <upi_id>`\nExample: `/withdraw 100 name@okaxis`", parse_mode="Markdown")
            return

        amount = int(context.args[0])
        upi_id = context.args[1]

        if amount < 50:
            await update.message.reply_text("❌ Minimum withdrawal amount ₹50 hai.")
            return

        current_bal = get_user_balance(sender_clean)
        if current_bal < amount:
            await update.message.reply_text(f"❌ Low Balance! Aapka balance ₹{current_bal} hai.")
            return

        # Wallet se balance deduct/hold karo
        set_user_balance(sender_clean, current_bal - amount)

        msg = (
            f"🔔 *WITHDRAWAL REQUEST RECEIVED*\n\n"
            f"• *User:* @{sender_clean}\n"
            f"• *Amount:* ₹{amount}\n"
            f"• *UPI ID:* `{upi_id}`\n"
            f"• *Remaining Balance:* ₹{current_bal - amount}\n\n"
            f"Admin verify karke jald payment bhej denge! ✅"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error in withdraw: {e}")
        await update.message.reply_text("⚠️ Withdrawal process karne mein error aaya.")

# ---------------- ADMIN COMMANDS ----------------

async def add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = (update.effective_user.username or "").lower().replace("@", "")
    if sender not in ADMINS:
        return

    if len(context.args) < 2 or not context.args[1].isdigit():
        await update.message.reply_text("⚠️ Format: `/addbal @username <amount>`")
        return

    target = context.args[0].lower().replace("@", "")
    amount = int(context.args[1])
    current = get_user_balance(target)
    set_user_balance(target, current + amount)

    await update.message.reply_text(f"✅ @{target} ke wallet mein ₹{amount} add ho gaye! Naya Balance: ₹{current + amount}")

async def cut_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = (update.effective_user.username or "").lower().replace("@", "")
    if sender not in ADMINS:
        return

    if len(context.args) < 2 or not context.args[1].isdigit():
        await update.message.reply_text("⚠️ Format: `/cutbal @username <amount>`")
        return

    target = context.args[0].lower().replace("@", "")
    amount = int(context.args[1])
    current = get_user_balance(target)
    new_bal = max(0, current - amount)
    set_user_balance(target, new_bal)

    await update.message.reply_text(f"✂️ @{target} ke wallet se ₹{amount} cut ho gaye. Naya Balance: ₹{new_bal}")

async def winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = (update.effective_user.username or "").lower().replace("@", "")
    if sender not in ADMINS:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format: `/win @winner_username`")
        return

    target = context.args[0].lower().replace("@", "")

    c.execute("SELECT * FROM games WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (target, target))
    game = c.fetchone()
    if not game:
        await update.message.reply_text("❌ Is user ka koi running match nahi mila.")
        return

    tot_pot = game["amount"] * 2
    commission = int(tot_pot * (COMMISSION_PERCENT / 100))
    winning_amount = tot_pot - commission

    current = get_user_balance(target)
    set_user_balance(target, current + winning_amount)

    c.execute("DELETE FROM games WHERE id = ?", (game["id"],))
    db.commit()

    msg = (
        f"🏆 *WINNER DECLARED!*\n\n"
        f"Winner: @{target}\n"
        f"Pot: ₹{tot_pot}\n"
        f"Commission: ₹{commission} (10%)\n"
        f"Winning Credited: *₹{winning_amount}* ✅"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def wallet_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = (update.effective_user.username or "").lower().replace("@", "")
    if sender not in ADMINS:
        return

    c.execute("SELECT username, balance FROM users WHERE balance > 0")
    rows = c.fetchall()
    if not rows:
        await update.message.reply_text("📊 Abhi kisi user ka balance add nahi hai.")
        return

    text = "📊 *USER BALANCES:*\n\n"
    for r in rows:
        text += f"• @{r['username']}: ₹{r['balance']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# Global Error Handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

# ---------------- MAIN FUNCTION ----------------
def main():
    Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Welcome new chat members
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("bal", balance))
    app.add_handler(CommandHandler("open", open_table))
    app.add_handler(CommandHandler("cancel", cancel_table))
    app.add_handler(CommandHandler("join", join_table))
    app.add_handler(CommandHandler("code", send_code))
    app.add_handler(CommandHandler("table", view_tables))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("addbal", add_balance))
    app.add_handler(CommandHandler("cutbal", cut_balance))
    app.add_handler(CommandHandler("win", winner))
    app.add_handler(CommandHandler("sheet", wallet_sheet))

    # Auto-Moderation & Triggers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), auto_moderation))

    app.add_error_handler(error_handler)

    logging.info("Bot is starting polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
        
