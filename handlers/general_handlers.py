import logging
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

import config
import data_manager
import game_logic

async def add_reaction_to_message(chat_id, message_id, emoji, context):
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/setMessageReaction"
    payload = {"chat_id": chat_id, "message_id": message_id, "reaction": [{"type": "emoji", "emoji": emoji}]}
    try:
        async with aiohttp.ClientSession() as session, session.post(url, json=payload) as response:
            if not response.ok:
                await context.bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=message_id)
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=message_id)

async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user: return

    user_id = str(update.message.from_user.id)
    chat_id = str(update.message.chat_id)
    
    tasks = data_manager.load_json(config.TASKS_FILE)
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)

    if chat_id not in tasks or user_id not in leaderboard.get(chat_id, {}): return
    if chat_id in leaderboard and user_id in leaderboard[chat_id]:
            leaderboard[chat_id][user_id]["name"] = update.message.from_user.first_name
            data_manager.save_json(leaderboard, config.LEADERBOARD_FILE)
    task = tasks[chat_id]
    progress = data_manager.load_json(config.PROGRESS_FILE)
    key = f"{chat_id}:{user_id}"
    current_progress = progress.get(key, 0)
    
    if current_progress >= task["goal"]: return # Задача уже выполнена

    game_logic.update_lifetime_stats(user_id, "date_check")
    
    new_progress = current_progress
    msg = update.message
    text_or_caption = msg.text or msg.caption or ""

    if task["type"] == "messages": new_progress += 1
    elif task["type"] == "voice" and msg.voice and msg.voice.duration >= task["goal"]: new_progress = task["goal"]
    elif task["type"] == "video_note" and msg.video_note and msg.video_note.duration >= task["goal"]: new_progress = task["goal"]
    elif task["type"] == "media" and (msg.photo or msg.video or msg.document): new_progress += 1
    elif task["type"] == "sticker" and msg.sticker: new_progress += 1
    elif task["type"] == "emoji" and task.get("emoji") in text_or_caption: new_progress += 1
    elif task["type"] == "photo" and msg.photo: new_progress = task["goal"]
    elif task["type"] == "video" and msg.video: new_progress += 1
    elif task["type"] == "animation" and msg.animation: new_progress = task["goal"]
    elif task["type"] == "question" and "?" in text_or_caption: new_progress += 1
    elif task["type"] == "keyword" and task.get("subtype") in text_or_caption.lower(): new_progress = task["goal"]
    elif task["type"] == "long_message" and len(text_or_caption) > 30: new_progress = task["goal"]
    elif task["type"] == "reply" and msg.reply_to_message: new_progress += 1
    elif task["type"] == "photo_with_caption" and msg.photo and msg.caption: new_progress = task["goal"]
    elif task["type"] == "location" and msg.location: new_progress = task["goal"]
    
    progress[key] = min(new_progress, task["goal"])
    data_manager.save_json(progress, config.PROGRESS_FILE)

    if progress[key] >= task["goal"]:
        leaderboard[chat_id][user_id]["points"] += task.get("bonus", 0)
        data_manager.save_json(leaderboard, config.LEADERBOARD_FILE)
        game_logic.update_lifetime_stats(user_id, "total_tasks_completed")
        await add_reaction_to_message(msg.chat_id, msg.message_id, "👍", context)
