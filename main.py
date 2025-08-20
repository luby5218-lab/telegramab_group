from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
import random
import os
from keep_alive import keep_alive

VERSION = "v2.0.0"

# 遊戲狀態：每個群組一個遊戲
group_games = {}

def generate_answer():
    digits = list(range(10))
    return "".join(str(digits.pop(random.randrange(len(digits)))) for _ in range(4))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("這個遊戲只能在群組玩！")
        return

    if chat_id in group_games:
        await update.message.reply_text("遊戲已經開始啦，請大家 /join 加入")
        return

    group_games[chat_id] = {
        "answer": generate_answer(),
        "players": [],
        "turn": 0,
    }
    await update.message.reply_text("群組遊戲開始！請大家輸入 /join 加入遊戲")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in group_games:
        await update.message.reply_text("還沒有遊戲，請先輸入 /start")
        return

    game = group_games[chat_id]
    if user.id not in [p["id"] for p in game["players"]]:
        game["players"].append({"id": user.id, "name": user.first_name})
        await update.message.reply_text(f"{user.first_name} 加入了遊戲！")
    else:
        await update.message.reply_text("你已經在遊戲中了")

async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in group_games:
        await update.message.reply_text("沒有進行中的遊戲，請先 /start")
        return

    game = group_games[chat_id]
    if len(game["players"]) == 0:
        await update.message.reply_text("還沒有人加入遊戲，請先 /join")
        return

    current_player = game["players"][game["turn"] % len(game["players"])]
    if user.id != current_player["id"]:
        await update.message.reply_text(f"現在輪到 {current_player['name']} 猜！")
        return

    if len(context.args) != 1 or not context.args[0].isdigit() or len(context.args[0]) != 4:
        await update.message.reply_text("請用格式 /guess 1234")
        return

    guess_num = context.args[0]
    if len(set(guess_num)) != 4:
        await update.message.reply_text("數字不能重複")
        return

    answer = game["answer"]
    A = sum(answer[i] == guess_num[i] for i in range(4))
    B = sum(answer[i] != guess_num[i] and guess_num[i] in answer for i in range(4))

    if A == 4:
        await update.message.reply_text(f"{user.first_name} 猜中了！答案是 {answer} 🎉 遊戲結束！")
        del group_games[chat_id]
    else:
        await update.message.reply_text(f"{guess_num} → {A}A{B}B")
        game["turn"] += 1
        next_player = game["players"][game["turn"] % len(game["players"])]
        await update.message.reply_text(f"輪到 {next_player['name']} 猜！")

async def quit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in group_games:
        await update.message.reply_text("目前沒有遊戲")
        return

    game = group_games[chat_id]
    before_count = len(game["players"])
    game["players"] = [p for p in game["players"] if p["id"] != user.id]

    if len(game["players"]) == 0:
        del group_games[chat_id]
        await update.message.reply_text(f"{user.first_name} 離開，遊戲結束")
    elif before_count != len(game["players"]):
        await update.message.reply_text(f"{user.first_name} 離開了遊戲")
    else:
        await update.message.reply_text("你不在遊戲裡")

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Bot version: {VERSION}")

if __name__ == "__main__":
    keep_alive()

    TOKEN = os.getenv("TOKEN")
    RENDER_URL = os.getenv("RENDER_URL")

    request = HTTPXRequest(connection_pool_size=20, pool_timeout=30.0)
    application = Application.builder().token(TOKEN).request(request).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("guess", guess))
    application.add_handler(CommandHandler("quit", quit))
    application.add_handler(CommandHandler("version", version))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
    )
