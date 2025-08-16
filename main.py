# group_bulls_cows.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import asyncio
import os
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.request import HTTPXRequest
from httpx import Timeout

# ====== 版本 ======
VERSION = "v2.0.0-group"

# ====== 遊戲狀態 ======
@dataclass
class GameState:
    answer: str
    players: List[int] = field(default_factory=list)
    started: bool = False
    turn_idx: int = 0
    history: List[Tuple[int, str, int, int]] = field(default_factory=list)  # (uid, guess, A, B)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

# 以 chat_id 管多局
chat_games: Dict[int, GameState] = {}

# ====== 工具 ======
def generate_answer(n: int = 4) -> str:
    digits = list(range(10))
    ans = "".join(str(digits.pop(random.randrange(len(digits)))) for _ in range(n))
    return ans

def calc_ab(answer: str, guess: str) -> Tuple[int, int]:
    # 正統：A = 位置對；B = 數字對但位置錯
    A = sum(a == b for a, b in zip(answer, guess))
    # 若都保證不重複，可用集合交集；這裡寫通用些
    common = sum(min(answer.count(ch), guess.count(ch)) for ch in set(guess))
    B = common - A
    return A, B

def mention(uid: int) -> str:
    return f"[user](tg://user?id={uid})"

# ====== Handlers ======
async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Bot version: {VERSION}")

async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("請在群組裡使用 /newgame。")
        return

    async with asyncio.Lock():  # 粗略避免同時多局
        chat_games[chat_id] = GameState(answer=generate_answer())
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✋ Join", callback_data="join"),
         InlineKeyboardButton("▶️ Start", callback_data="start")]
    ])
    await update.message.reply_text(
        "新局已建立！按「Join」報名，創局者或管理員按「Start」開始。\n"
        "猜測時請用 `/guess 1234`（建議保留隱私模式）。",
        reply_markup=kb
    )

async def cb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat = query.message.chat
    chat_id = chat.id
    user_id = query.from_user.id

    if chat_id not in chat_games:
        await query.edit_message_text("目前沒有進行中的大廳，請用 /newgame 開新局。")
        return
    gs = chat_games[chat_id]

    if query.data == "join":
        async with gs.lock:
            if gs.started:
                await query.answer("遊戲已開始。", show_alert=True)
                return
            if user_id not in gs.players:
                gs.players.append(user_id)
        await query.answer("已加入。")
        await query.message.reply_text(f"{mention(user_id)} 加入了這局。", parse_mode="Markdown")
    elif query.data == "start":
        async with gs.lock:
            if gs.started:
                await query.answer("遊戲已開始。", show_alert=True)
                return
            if len(gs.players) < 2:
                await query.answer("至少需要 2 名玩家。", show_alert=True)
                return
            gs.started = True
            gs.turn_idx = 0
            current_uid = gs.players[gs.turn_idx]
        await query.message.reply_text(
            f"遊戲開始！目標為 4 個不重複數字。\n"
            f"輪到 {mention(current_uid)}，請用 `/guess 1234`。",
            parse_mode="Markdown"
        )

async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id not in chat_games:
        await update.message.reply_text("目前沒有大廳，請用 /newgame 開新局。")
        return
    gs = chat_games[chat_id]
    async with gs.lock:
        if gs.started:
            await update.message.reply_text("遊戲已開始，無法加入。")
            return
        if user_id not in gs.players:
            gs.players.append(user_id)
    await update.message.reply_text(f"{mention(user_id)} 加入了這局。", parse_mode="Markdown")

async def cmd_startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in chat_games:
        await update.message.reply_text("沒有大廳可開始，請先 /newgame。")
        return
    gs = chat_games[chat_id]
    async with gs.lock:
        if gs.started:
            await update.message.reply_text("已經開始了。")
            return
        if len(gs.players) < 2:
            await update.message.reply_text("至少需要 2 名玩家。")
            return
        gs.started = True
        gs.turn_idx = 0
        current_uid = gs.players[gs.turn_idx]
    await update.message.reply_text(
        f"遊戲開始！輪到 {mention(current_uid)}，請用 `/guess 1234`。",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in chat_games:
        await update.message.reply_text("這個群目前沒有進行中的遊戲。")
        return
    gs = chat_games[chat_id]
    players_txt = ", ".join(mention(uid) for uid in gs.players) or "（無人）"
    turn_uid = gs.players[gs.turn_idx] if (gs.players and gs.started) else None
    await update.message.reply_text(
        "狀態：\n"
        f"- 是否開始：{gs.started}\n"
        f"- 玩家：{players_txt}\n"
        + (f"- 當前輪到：{mention(turn_uid)}\n" if turn_uid else "")
        + f"- 猜測次數：{len(gs.history)}",
        parse_mode="Markdown"
    )

async def cmd_endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_games:
        ans = chat_games[chat_id].answer
        del chat_games[chat_id]
        await update.message.reply_text(f"本局結束，答案為 {ans}")
    else:
        await update.message.reply_text("沒有進行中的遊戲。")

async def cmd_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("此指令針對群組遊戲，請在群組使用。")
        return

    if chat_id not in chat_games:
        await update.message.reply_text("這個群目前沒有進行中的遊戲，請先 /newgame。")
        return
    gs = chat_games[chat_id]

    if not context.args:
        await update.message.reply_text("用法：`/guess 1234`", parse_mode="Markdown")
        return

    guess = context.args[0].strip()
    if not guess.isdigit() or len(guess) != 4 or len(set(guess)) != 4:
        await update.message.reply_text("請輸入 4 位不重複數字，例如：`/guess 1234`", parse_mode="Markdown")
        return

    async with gs.lock:
        if not gs.started:
            await update.message.reply_text("遊戲尚未開始，請先 /startgame。")
            return
        if user_id not in gs.players:
            await update.message.reply_text("你不在本局玩家名單內，請先 /join。")
            return
        # 檢查回合
        current_uid = gs.players[gs.turn_idx]
        if user_id != current_uid:
            await update.message.reply_text(f"現在不是你的回合，輪到的是 {mention(current_uid)}。", parse_mode="Markdown")
            return

        A, B = calc_ab(gs.answer, guess)
        gs.history.append((user_id, guess, A, B))

        if A == 4:
            ans = gs.answer
            del chat_games[chat_id]
            await update.message.reply_text(
                f"{mention(user_id)} 猜中！答案是 {ans} 🎉\n本局結束！",
                parse_mode="Markdown"
            )
            return
        else:
            # 換下一位
            gs.turn_idx = (gs.turn_idx + 1) % len(gs.players)
            next_uid = gs.players[gs.turn_idx]

    await update.message.reply_text(
        f"{mention(user_id)} ➜ `{guess}` → `{A}A{B}B`\n"
        f"輪到 {mention(next_uid)}，請用 `/guess 1234`。",
        parse_mode="Markdown"
    )

# ====== 程式進入點（沿用你的 run_webhook 風格） ======
def main():
    # 你已在 Render 設置 TOKEN / RENDER_URL
    TOKEN = os.getenv("TOKEN")
    RENDER_URL = os.getenv("RENDER_URL")
    if not TOKEN or not RENDER_URL:
        raise RuntimeError("請設定環境變數 TOKEN / RENDER_URL")

    request = HTTPXRequest(connection_pool_size=20, pool_timeout=30.0, timeout=Timeout(10.0, connect=10.0))
    application = Application.builder().token(TOKEN).request(request).build()

    # 指令
    application.add_handler(CommandHandler("version", cmd_version))
    application.add_handler(CommandHandler("newgame", cmd_newgame))
    application.add_handler(CommandHandler("join", cmd_join))
    application.add_handler(CommandHandler("startgame", cmd_startgame))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("endgame", cmd_endgame))
    application.add_handler(CommandHandler("guess", cmd_guess))
    # 按鈕
    application.add_handler(CallbackQueryHandler(cb_buttons))

    # 自帶 HTTP 伺服器（不需要 Flask）
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        url_path=TOKEN,                     # 避免被掃
        webhook_url=f"{RENDER_URL}/{TOKEN}" # BotFather 的 getWebhookInfo 會看到這個
    )

if __name__ == "__main__":
    main()
