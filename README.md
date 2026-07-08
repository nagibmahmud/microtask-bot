# Microtask Telegram Bot

A Telegram bot for distributing small tasks (microtasks) to users, who claim and
complete them for points, with a leaderboard.

## Features
- `/start` — register and see help
- `/tasks` — list open microtasks
- `/take <id>` — claim a task
- `/mytasks` — your claimed tasks
- `/done <id>` — submit a claimed task for admin review
- `/balance` — your points
- `/leaderboard` — top users
- Admin: `/addtask <reward> <title>`, `/verify <approve|reject> <id>`, `/broadcast <msg>`

## Setup
1. Talk to [@BotFather](https://t.me/BotFather) on Telegram, create a bot, and copy the token.
2. (Optional) Get your Telegram user id from [@userinfobot](https://t.me/userinfobot) to be an admin.
3. Create a `.env` file in this folder:

```
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789
```

4. Install dependencies and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Data is stored in `data.json` (created automatically).

## Notes
- The bot uses long polling, so no public URL is required.
- For production, run it with a process manager (e.g. `pm2`, `systemd`, or a Docker container).
