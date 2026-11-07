import sqlite3, os, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- DUMMY SERVER FOR RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# --- BOT CONFIGURATION ---
BOT_TOKEN = "9076286788:AAFcflbMCKSdMVvkkt3ajfacE6KRyLYAuLY"
ADMIN_USERNAMES = ["Raj1235567"]
COMMISSION_PERCENT = 10
UPI_ID = "choudharyvikash4705-2@okicici"
PAYEE_NAME = "Vikash Choudhary"

conn = sqlite3.connect("ludo_data.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS wallets (username TEXT PRIMARY KEY, balance INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, opponent TEXT, amount INTEGER, status TEXT, code TEXT)")
conn.commit()

def get_bal(u):
    cur.execute("SELECT balance FROM wallets WHERE username = ?", (u.lower(),))
    r = cur.fetchone()
    return r[0] if r else 0

def set_bal(u, amt):
    new_b = get_bal(u) + amt
    cur.execute("INSERT OR REPLACE INTO wallets (username, balance) VALUES (?, ?)", (u.lower(), new_b))
    conn.commit()
    return new_b

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎲 *LUDO BETTING BOT READY*\n\n"
        "📌 *User Commands:*\n"
        "• `/bal` - Check wallet balance\n"
        "• `/open <amt>` - Create challenge\n"
        "• `/join <host>` - Join challenge\n"
        "• `/code <code>` - Room code set karein\n"
        "• `/cancel` - Cancel active challenge\n"
        "• `/table` - Running matches list\n"
        "• `/rules` - Game guidelines\n"
        "• `/qr` - Deposit scanner\n\n"
        "👑 *Admin Commands:*\n"
        "• `/addbal @user <amt>`\n"
        "• `/cutbal @user <amt>`\n"
        "• `/win @user`\n"
        "• `/sheet`"
    )
    await u.message.reply_text(msg, parse_mode="Markdown")

async def rules(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📜 *GAME RULES:*\n"
        "1. Match over hone par clean screenshot bhejhein.\n"
        "2. Fake screenshot ya fraud par balance zero aur ban lagaya jayega.\n"
        "3. Har match jeetne par 10% admin commission kategi."
    )
    await u.message.reply_text(msg, parse_mode="Markdown")

async def bal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    un = u.effective_user.username
    if not un: return await u.message.reply_text("Telegram username set karein.")
    await u.message.reply_text(f"💰 Balance: ₹{get_bal(un)}")

async def addbal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES] or len(c.args) < 2: return
    user, amt = c.args[0].replace("@", "").lower(), int(c.args[1])
    nb = set_bal(user, amt)
    await u.message.reply_text(f"✅ ₹{amt} added to @{user}. New: ₹{nb}")

async def cutbal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES] or len(c.args) < 2: return
    user, amt = c.args[0].replace("@", "").lower(), int(c.args[1])
    nb = set_bal(user, -amt)
    await u.message.reply_text(f"✂️ ₹{amt} cut from @{user}. New: ₹{nb}")

async def sheet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    cur.execute("SELECT username, balance FROM wallets WHERE balance > 0")
    rows = cur.fetchall()
    if not rows: return await u.message.reply_text("Koi active balance nahi mila.")
    msg = "📊 *WALLET SHEET:*\n" + "\n".join([f"• @{r[0]}: ₹{r[1]}" for r in rows])
    await u.message.reply_text(msg, parse_mode="Markdown")

async def open_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    un = u.effective_user.username
    if not un or not c.args: return await u.message.reply_text("Usage: `/open 100`")
    amt = int(c.args[0])
    if get_bal(un) < amt: return await u.message.reply_text("Balance kam hai. Deposit karein.")
    cur.execute("SELECT id FROM matches WHERE host = ? AND status IN ('WAITING', 'PLAYING')", (un.lower(),))
    if cur.fetchone(): return await u.message.reply_text("Aapka pehle se ek match open hai.")
    cur.execute("INSERT INTO matches (host, opponent, amount, status, code) VALUES (?, '', ?, 'WAITING', '')", (un.lower(), amt))
    conn.commit()
    await u.message.reply_text(f"🎲 *TABLE OPENED!*\nHost: @{un}\nAmount: ₹{amt}\nJoin karne ke liye: `/join {un}`", parse_mode="Markdown")

async def join_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    un = u.effective_user.username
    if not un or not c.args: return await u.message.reply_text("Usage: `/join host_username`")
    host = c.args[0].replace("@", "").lower()
    if host == un.lower(): return await u.message.reply_text("Khud ka match join nahi kar sakte.")
    cur.execute("SELECT id, amount FROM matches WHERE host = ? AND status = 'WAITING'", (host,))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Table nahi mila ya join ho chuka hai.")
    mid, amt = m
    if get_bal(un) < amt: return await u.message.reply_text("Balance insufficient hai.")
    set_bal(host, -amt)
    set_bal(un, -amt)
    cur.execute("UPDATE matches SET opponent = ?, status = 'PLAYING' WHERE id = ?", (un.lower(), mid))
    conn.commit()
    await u.message.reply_text(f"⚔️ *MATCH STARTED!*\nHost: @{host} vs @{un}\nBet: ₹{amt}\nHost room code daalein: `/code 12345678`", parse_mode="Markdown")

async def set_code(u: Update, c: ContextTypes.DEFAULT_TYPE):
    un = u.effective_user.username
    if not un or not c.args: return await u.message.reply_text("Usage: `/code 12345678`")
    code = c.args[0]
    cur.execute("SELECT opponent FROM matches WHERE host = ? AND status = 'PLAYING'", (un.lower(),))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Koi active playing match nahi mila.")
    cur.execute("UPDATE matches SET code = ? WHERE host = ? AND status = 'PLAYING'", (code, un.lower()))
    conn.commit()
    await u.message.reply_text(f"🔑 *ROOM CODE:*\n`{code}`\n@{m[0]} join karein!", parse_mode="Markdown")

async def cancel_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    un = u.effective_user.username
    if not un: return
    cur.execute("SELECT id FROM matches WHERE host = ? AND status = 'WAITING'", (un.lower(),))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Koi open match nahi mila jise cancel karein.")
    cur.execute("DELETE FROM matches WHERE id = ?", (m[0],))
    conn.commit()
    await u.message.reply_text("✅ Table cancel kar diya gaya.")

async def table(u: Update, c: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT host, opponent, amount, status, code FROM matches WHERE status != 'COMPLETED'")
    rows = cur.fetchall()
    if not rows: return await u.message.reply_text("Koi active match nahi hai.")
    msg = "🎲 *ACTIVE TABLES*\n\n" + "\n".join([f"• @{r[0]} vs @{r[1]} | ₹{r[2]} | Code: {r[4]}" for r in rows])
    await u.message.reply_text(msg, parse_mode="Markdown")

async def win(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES] or not c.args: return
    winner = c.args[0].replace("@", "").lower()
    cur.execute("SELECT id, amount FROM matches WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (winner, winner))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Active match nahi mila.")
    mid, amt = m
    prize = (amt * 2) - int((amt * 2) * (COMMISSION_PERCENT / 100))
    nb = set_bal(winner, prize)
    cur.execute("DELETE FROM matches WHERE id = ?", (mid,))
    conn.commit()
    await u.message.reply_text(f"🏆 *WINNER:* @{winner}\nPrize: ₹{prize} credit kar diya gaya. New Bal: ₹{nb}", parse_mode="Markdown")

async def qr_send(u: Update, c: ContextTypes.DEFAULT_TYPE):
    cap = f"💳 *DEPOSIT QR*\nName: *{PAYEE_NAME}*\nUPI ID: `{UPI_ID}`\n\nPayment karke screenshot yahan bhejein."
    if os.path.exists("qr.jpg"):
        with open("qr.jpg", "rb") as p: await u.message.reply_photo(photo=p, caption=cap, parse_mode="Markdown")
    else:
        await u.message.reply_text(cap, parse_mode="Markdown")

async def text_guard(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text: return
    t = u.message.text.lower()
    if any(k in t for k in ["qr", "scanner", "payment", "deposit", "pay"]):
        await qr_send(u, c)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    for cmd, fn in [
        ("start", start), ("rules", rules), ("bal", bal), ("addbal", addbal),
        ("cutbal", cutbal), ("sheet", sheet), ("open", open_match), ("join", join_match),
        ("code", set_code), ("cancel", cancel_match), ("table", table), ("win", win), ("qr", qr_send)
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_guard))
    app.run_polling()
    
