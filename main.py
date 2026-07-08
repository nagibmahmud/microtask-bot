import json
import os
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

DATA_FILE = os.getenv("DATA_FILE", "data.json")

lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "tasks": [], "next_task_id": 1}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_admin(user_id):
    return user_id in ADMIN_IDS


def ensure_user(data, user):
    uid = str(user.id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "points": 0,
            "completed": [],
        }
    return data["users"][uid]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with lock:
        data = load_data()
        ensure_user(data, user)
        save_data(data)
    await update.message.reply_text(
        "👋 Welcome to the Microtask Bot!\n\n"
        "Post small tasks, claim them, and earn points.\n\n"
        "Commands:\n"
        "/tasks - list open tasks\n"
        "/take <id> - claim a task\n"
        "/mytasks - your claimed tasks\n"
        "/done <id> - submit a task for review\n"
        "/balance - your points\n"
        "/leaderboard - top users\n\n"
        "Admins can use /addtask, /verify, /broadcast."
    )


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with lock:
        data = load_data()
        open_tasks = [t for t in data["tasks"] if t["status"] == "open"]
    if not open_tasks:
        await update.message.reply_text("No open tasks right now. Check back later!")
        return
    lines = ["📋 *Open microtasks:*"]
    for t in open_tasks:
        lines.append(
            f"`#{t['id']}` {t['title']}\n"
            f"   reward: *{t['reward']}* pts · /take {t['id']}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /take <id>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task id.")
        return
    user = update.effective_user
    with lock:
        data = load_data()
        ensure_user(data, user)
        task = next((t for t in data["tasks"] if t["id"] == tid), None)
        if not task:
            await update.message.reply_text("Task not found.")
            return
        if task["status"] != "open":
            await update.message.reply_text("That task is no longer open.")
            return
        task["status"] = "claimed"
        task["claimed_by"] = user.id
        task["claimed_at"] = now_iso()
        save_data(data)
    await update.message.reply_text(
        f"✅ You claimed task #{tid}: {task['title']}.\n"
        f"Finish it and run /done {tid} to submit for review."
    )


async def mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with lock:
        data = load_data()
        mine = [
            t
            for t in data["tasks"]
            if t.get("claimed_by") == user.id and t["status"] in ("claimed", "pending")
        ]
    if not mine:
        await update.message.reply_text("You have no claimed tasks.")
        return
    lines = ["🗂 *Your tasks:*"]
    for t in mine:
        lines.append(f"`#{t['id']}` {t['title']} — _{t['status']}_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /done <id>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task id.")
        return
    user = update.effective_user
    with lock:
        data = load_data()
        task = next((t for t in data["tasks"] if t["id"] == tid), None)
        if not task or task.get("claimed_by") != user.id:
            await update.message.reply_text("You haven't claimed that task.")
            return
        if task["status"] == "pending":
            await update.message.reply_text("Already submitted, waiting for review.")
            return
        task["status"] = "pending"
        save_data(data)
    if ADMIN_IDS:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tid}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tid}"),
                ]
            ]
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"Review task #{tid} from {user.first_name}:\n{task['title']}",
                    reply_markup=kb,
                )
            except Exception:
                pass
    await update.message.reply_text("📤 Submitted! An admin will review it soon.")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with lock:
        data = load_data()
        u = ensure_user(data, user)
        pts = u["points"]
    await update.message.reply_text(f"💰 Your balance: *{pts}* points", parse_mode="Markdown")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with lock:
        data = load_data()
        ranked = sorted(
            data["users"].values(), key=lambda u: u.get("points", 0), reverse=True
        )[:10]
    if not ranked:
        await update.message.reply_text("No scores yet.")
        return
    lines = ["🏆 *Leaderboard:*"]
    for i, u in enumerate(ranked, 1):
        name = u.get("first_name") or u.get("username") or f"user{u['id']}"
        lines.append(f"{i}. {name} — {u.get('points', 0)} pts")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addtask <reward> <title...>")
        return
    try:
        reward = int(context.args[0])
        title = " ".join(context.args[1:])
    except ValueError:
        await update.message.reply_text("First argument must be a reward number.")
        return
    if not title:
        await update.message.reply_text("Provide a task title.")
        return
    with lock:
        data = load_data()
        tid = data["next_task_id"]
        data["tasks"].append(
            {
                "id": tid,
                "title": title,
                "reward": reward,
                "status": "open",
                "created_at": now_iso(),
                "claimed_by": None,
                "claimed_at": None,
            }
        )
        data["next_task_id"] = tid + 1
        save_data(data)
    await update.message.reply_text(f"➕ Added task #{tid}: {title} ({reward} pts)")


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /verify <approve|reject> <id>")
        return
    action = context.args[0].lower()
    try:
        tid = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid task id.")
        return
    await _resolve_task(update, context, tid, action == "approve")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Admin only.")
        return
    action, tid = query.data.split(":")
    tid = int(tid)
    await _resolve_task(query, context, tid, action == "approve", edit=True)


async def _resolve_task(target, context, tid, approve, edit=False):
    with lock:
        data = load_data()
        task = next((t for t in data["tasks"] if t["id"] == tid), None)
        if not task:
            msg = "Task not found."
        elif task["status"] != "pending":
            msg = f"Task #{tid} is not awaiting review ({task['status']})."
        else:
            uid = str(task["claimed_by"])
            if approve:
                task["status"] = "completed"
                if uid in data["users"]:
                    data["users"][uid]["points"] += task["reward"]
                    data["users"][uid]["completed"].append(tid)
                msg = f"✅ Task #{tid} approved. +{task['reward']} pts."
            else:
                task["status"] = "open"
                task["claimed_by"] = None
                msg = f"❌ Task #{tid} rejected. Reopened."
            save_data(data)
    if edit:
        await target.edit_message_text(msg)
    else:
        await target.message.reply_text(msg)


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    with lock:
        data = load_data()
        users = list(data["users"].values())
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(u["id"], f"📢 {text}")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"Broadcast sent to {sent} users.")


def main():
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN in your environment / .env file.")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("take", take))
    app.add_handler(CommandHandler("mytasks", mytasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button))

    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
        if render_host:
            webhook_url = f"https://{render_host}"
    port = int(os.getenv("PORT", "10000"))
    if webhook_url:
        print(f"Microtask bot is running via webhook on {webhook_url}...")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=BOT_TOKEN,
            webhook_url=f"{webhook_url}/{BOT_TOKEN}",
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        print("Microtask bot is running (polling)...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
