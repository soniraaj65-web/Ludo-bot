import sqlite3, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "9076286788:AAFcfibMCKsdMVvkkt3ajfacE6KRyLYAuLY"
ADMIN_USERNAMES = ["Raj1235567"]
COMMISSION_PERCENT = 10
UPI_ID = "choudharyvikash4705-2@okicici"
PAYEE_NAME = "Vikash Choudhary"

conn = sqlite3.connect("ludo_data.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS wallets (username TEXT PRIMARY KEY, balance INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, opponent TEXT, amount INTEGER, code TEXT, status TEXT)")
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
    msg = ("👑 *THE LUDO EMPIRE BOT* 👑\n\n"
           "🎮 *Commands:*\n"
           "👉 `/bal` - Wallet balance\n"
           "👉 `/open <amt>` - Create match\n"
           "👉 `/join <host>` - Join match\n"
           "👉 `/code <code>` - Room code\n"
           "👉 `/cancel` - Cancel open match\n"
           "👉 `/table` - Active tables\n"
           "👉 `/rules` - Group rules\n"
           "👉 `/qr` - Deposit QR\n\n"
           "🛡️ *Admin:*\n"
           "👉 `/addbal <user> <amt>`\n"
           "👉 `/cutbal <user> <amt>`\n"
           "👉 `/win <user>`\n"
           "👉 `/sheet`")
    await u.message.reply_text(msg, parse_mode="Markdown")

async def rules(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("📜 *RULES:*\n1. Result ke 5 min me screenshot dalein.\n2. 3 min me room code generate karein.\n3. Disconnect par samne wala winner hoga.")

async def bal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user.username
    if not user: return await u.message.reply_text("Telegram username set karein.")
    await u.message.reply_text(f"👤 @{user}\n💰 Balance: ₹{get_bal(user)}")

async def addbal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    if len(c.args) < 2: return await u.message.reply_text("Usage: `/addbal user 100`")
    tar, amt = c.args[0].replace("@",""), int(c.args[1])
    tot = set_bal(tar, amt)
    await u.message.reply_text(f"✅ ₹{amt} added to @{tar}. Total: ₹{tot}")

async def cutbal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    if len(c.args) < 2: return await u.message.reply_text("Usage: `/cutbal user 50`")
    tar, amt = c.args[0].replace("@",""), int(c.args[1])
    tot = set_bal(tar, -amt)
    await u.message.reply_text(f"🔻 ₹{amt} cut from @{tar}. Total: ₹{tot}")

async def sheet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    cur.execute("SELECT username, balance FROM wallets WHERE balance > 0")
    rows = cur.fetchall()
    t = "📊 *LEDGER SHEET*\n\n" + "\n".join([f"• @{r[0]}: ₹{r[1]}" for r in rows])
    await u.message.reply_text(t if rows else "Koi balance nahi hai.", parse_mode="Markdown")

async def open_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user.username
    if not user or not c.args: return await u.message.reply_text("Usage: `/open 100`")
    amt = int(c.args[0])
    if get_bal(user) < amt: return await u.message.reply_text(f"Kam balance! Deposit ke liye `/qr` karein.")
    cur.execute("SELECT id FROM matches WHERE host = ? AND status = 'OPEN'", (user.lower(),))
    if cur.fetchone(): return await u.message.reply_text("Ek match already open hai.")
    cur.execute("INSERT INTO matches (host, opponent, amount, code, status) VALUES (?, '', ?, '', 'OPEN')", (user.lower(), amt))
    conn.commit()
    win_amt = (amt * 2) - int((amt * 2) * (COMMISSION_PERCENT / 100))
    await u.message.reply_text(f"🎲 *NEW MATCH*\nHost: @{user}\nEntry: ₹{amt}\nWin: ₹{win_amt}\n👉 `/join {user}`", parse_mode="Markdown")

async def join_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user.username
    if not user or not c.args: return
    host = c.args[0].replace("@","").lower()
    if host == user.lower(): return
    cur.execute("SELECT id, amount FROM matches WHERE host = ? AND status = 'OPEN'", (host,))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Match open nahi hai.")
    mid, amt = m
    if get_bal(user) < amt: return await u.message.reply_text(f"Balance kam hai! Required: ₹{amt}")
    set_bal(host, -amt); set_bal(user, -amt)
    cur.execute("UPDATE matches SET opponent = ?, status = 'PLAYING' WHERE id = ?", (user.lower(), mid))
    conn.commit()
    await u.message.reply_text(f"⚔️ *MATCH FIXED*\n🔴 @{host} vs 🔵 @{user}\nEntry: ₹{amt} deducted.\n👉 @{host} code dalein: `/code 1234`", parse_mode="Markdown")

async def set_code(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user.username
    if not c.args: return
    code = c.args[0]
    cur.execute("SELECT id FROM matches WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (user.lower(), user.lower()))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Running match nahi mila.")
    cur.execute("UPDATE matches SET code = ? WHERE id = ?", (code, m[0]))
    conn.commit()
    await u.message.reply_text(f"🎯 *ROOM CODE:* `{code}`\nGame start karein!", parse_mode="Markdown")

async def cancel_match(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user.username
    cur.execute("DELETE FROM matches WHERE host = ? AND status = 'OPEN'", (user.lower(),))
    conn.commit()
    await u.message.reply_text("Open match cancel ho gaya.")

async def table(u: Update, c: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT host, opponent, amount, status, code FROM matches WHERE status != 'COMPLETED'")
    rows = cur.fetchall()
    if not rows: return await u.message.reply_text("Koi active match nahi hai.")
    msg = "🎲 *ACTIVE TABLES*\n\n" + "\n".join([f"• @{r[0]} vs @{r[1]} | ₹{r[2]} | Code: {r[4]}" for r in rows])
    await u.message.reply_text(msg, parse_mode="Markdown")

async def win(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if (u.effective_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES] or not c.args: return
    winner = c.args[0].replace("@","").lower()
    cur.execute("SELECT id, amount FROM matches WHERE (host = ? OR opponent = ?) AND status = 'PLAYING'", (winner, winner))
    m = cur.fetchone()
    if not m: return await u.message.reply_text("Active match nahi mila.")
    mid, amt = m
    prize = (amt * 2) - int((amt * 2) * (COMMISSION_PERCENT / 100))
    nb = set_bal(winner, prize)
    cur.execute("DELETE FROM matches WHERE id = ?", (mid,))
    conn.commit()
    await u.message.reply_text(f"🏆 *WINNER:* @{winner}\n💰 Prize: +₹{prize}\nNew Balance: ₹{nb}", parse_mode="Markdown")

async def qr_send(u: Update, c: ContextTypes.DEFAULT_TYPE):
    cap = f"💳 *DEPOSIT QR*\nName: *{PAYEE_NAME}*\nUPI: `{UPI_ID}`\nScreenshot group me dalein."
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
