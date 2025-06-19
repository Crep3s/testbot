from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ChatType
from datetime import datetime

import config
import data_manager
import utils

# Определяем состояние для ConversationHandler
SEASON_STATE = range(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    await update.message.reply_text(
        "Ласкаво просимо до гри Найдовший песюн! Виберіть один із запропонованих варіантів для управління грою",
        reply_markup=utils.get_main_keyboard()
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Ця команда працює тільки в групах.")
        return
    
    user = update.effective_user
    chat_id = str(update.effective_chat.id)
    user_id = str(user.id)
    
    data = data_manager.load_json(config.LEADERBOARD_FILE)
    data.setdefault(chat_id, {})

    if user_id in data[chat_id]:
        await update.message.reply_text(f"\u200E{user.full_name}, ти вже в грі.")
        return

    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    medals = lifetime.get(user_id, {}).get("medals", {})
    
    season_cache = data_manager.load_json(config.SEASON_CACHE_FILE)
    points = season_cache.get(chat_id, {}).pop(user_id, 0)
    data_manager.save_json(season_cache, config.SEASON_CACHE_FILE)

    data[chat_id][user_id] = {
        "name": user.first_name, "points": points,
        "last_delta": 0, "medals": medals
    }
    data_manager.save_json(data, config.LEADERBOARD_FILE)
    await update.message.reply_text(f"\u200E{user.first_name} приєднався до гри! Песюн: {points} см")


async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Ця команда працює тільки в групі.")
        return

    user = update.effective_user
    chat_id = str(update.effective_chat.id)
    user_id = str(user.id)
    
    data = data_manager.load_json(config.LEADERBOARD_FILE)

    if chat_id in data and user_id in data[chat_id]:
        leaderboard_user = data[chat_id][user_id]
        
        lifetime = data_manager.load_json(config.LIFETIME_FILE)
        user_lifetime = lifetime.setdefault(user_id, {
            "name": user.first_name, "medals": {"gold": 0, "silver": 0, "bronze": 0}
        })
        user_lifetime["name"] = user.first_name
        user_lifetime.setdefault("total_points", 0)
        user_lifetime["total_points"] += leaderboard_user.get("points", 0)

        lb_medals = leaderboard_user.get("medals", {})
        user_lifetime.setdefault("medals", {})
        for medal, count in lb_medals.items():
            user_lifetime["medals"][medal] = user_lifetime["medals"].get(medal, 0) + count

        
        data_manager.save_json(lifetime, config.LIFETIME_FILE)

        del data[chat_id][user_id]
        
        season_cache = data_manager.load_json(config.SEASON_CACHE_FILE)
        season_cache.setdefault(chat_id, {})[user_id] = leaderboard_user.get("points", 0)
        data_manager.save_json(season_cache, config.SEASON_CACHE_FILE)
        data_manager.save_json(data, config.LEADERBOARD_FILE)

        await update.message.reply_text(f"\u200E{user.first_name} вийшов з гри.")
    else:
        await update.message.reply_text("Тебе немає в грі.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    user_id = str(update.effective_user.id)
    chat_id = str(config.GROUP_CHAT_ID)

    if not utils.check_registered(user_id):
        await update.message.reply_text("Ви ще не зареєстровані. Напишіть /join у групі.", reply_markup=utils.get_main_keyboard())
        return

    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE).get(chat_id, {})
    lifetime = data_manager.load_json(config.LIFETIME_FILE).get(user_id, {})
    
    season_points = leaderboard.get(user_id, {}).get("points", 0)
    total_past_points = lifetime.get("total_points", 0)
    total_points = total_past_points + season_points
    medals = utils.format_medals(leaderboard.get(user_id, {}).get("medals", lifetime.get("medals", {})))

    text = (
        f"🙎‍♂️ Ваш профіль\n\n"
        f"{medals} {utils.safe_username(update.effective_user.first_name)}\n"
        f"🔢 Усього сантиметрів: {total_points} см\n"
        f"✅ Завдань виконано: {lifetime.get('total_tasks_completed', 0)}\n"
        f"❌ Завдань пропущено: {lifetime.get('failed_tasks', 0)}\n"
        f"📅 Днів активності: {lifetime.get('days_played', 0)}\n"
        f"🔥 Серія: {lifetime.get('current_streak', 0)} (макс: {lifetime.get('streak_max', 0)})"
    )
    await update.message.reply_text(text, reply_markup=utils.get_main_keyboard())

async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    user_id = str(update.effective_user.id)

    if not utils.check_registered(user_id):
        await update.message.reply_text("Ви ще не зареєстровані. Напишіть /join у групі.", reply_markup=utils.get_main_keyboard())
        return
    
    inv = data_manager.load_json(config.INVENTORY_FILE).get(user_id, [])
    if not inv:
        await update.message.reply_text("🎒 Ваш інвентар порожній.", reply_markup=utils.get_main_keyboard())
        return

    text = "🎒 Ваш інвентар:\n"
    for item_id in inv:
        item = config.ITEM_CATALOG.get(item_id, {"name": f"❓ Невідомий предмет: {item_id}", "description": ""})
        text += f"- {item['name']}: {item['description']}\n"
    await update.message.reply_text(text, reply_markup=utils.get_main_keyboard())

async def season_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    await update.message.reply_text("Введіть номер сезону:", reply_markup=ReplyKeyboardRemove())
    return SEASON_STATE

async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num_str = update.message.text.strip()
    if not num_str.isdigit() or int(num_str) <= 0:
        await update.message.reply_text("Некоректний номер.", reply_markup=utils.get_main_keyboard())
        return ConversationHandler.END
    
    num = int(num_str)
    user_id = str(update.effective_user.id)
    chat_id = str(config.GROUP_CHAT_ID)
    
    history = data_manager.load_json(config.SEASONS_FILE).get(chat_id, {}).get("history", [])
    if not history:
        await update.message.reply_text("Історія сезонів порожня.", reply_markup=utils.get_main_keyboard())
        return ConversationHandler.END

    matched_season = next((s for s in history if s.get("season") == num), None)
    if not matched_season:
        await update.message.reply_text("Сезон не знайдено.", reply_markup=utils.get_main_keyboard())
        return ConversationHandler.END

    text = f"🏁 Сезон {num}\n\nТоп-3 песюна:\n"
    for winner in matched_season["winners"]:
        name = utils.safe_username(winner["name"])
        emoji = config.MEDAL_EMOJIS.get(winner["medal"], "")
        item = config.ITEM_CATALOG.get(config.ITEM_REWARDS.get(winner["medal"]), {"name": "Невідомий приз"})
        stats = winner.get("stats", {})
        stats_summary = (
            f"  🧾 Завдань: {stats.get('total_tasks_completed', 0)} | "
            f"Днів активності: {stats.get('days_played', 0)} | "
            f"Серія: {stats.get('streak_max', 0)} днів"
        )
        points = winner.get("points", 0)
        text += f"\u200E{emoji} {name} — {points} см. Нагорода: {item['name']}\n{stats_summary}\n\n"

    scores = matched_season.get("scores", {})
    if scores and user_id in scores:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]["points"], reverse=True)
        user_place = next(((idx, data) for idx, (uid, data) in enumerate(sorted_scores, 1) if uid == user_id), None)
        if user_place:
            text += f"\n📌 Ви зайняли {user_place[0]}-е місце з песюном {user_place[1].get('points', 0)} см."
    
    ended_at_iso = matched_season.get("ended_at")
    if ended_at_iso:
        try:
            ended_fmt = datetime.fromisoformat(ended_at_iso).strftime("%d.%m.%Y %H:%M")
            text += f"\n📅 Завершено: {ended_fmt}"
        except ValueError: pass

    await update.message.reply_text(text, reply_markup=utils.get_main_keyboard())
    return ConversationHandler.END

async def show_leaderboard_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    data = data_manager.load_json(config.LEADERBOARD_FILE)
    chat_id = next(iter(data), None)

    if not chat_id or chat_id not in data:
        await update.message.reply_text("Таблиця лідерів поки порожня.")
        return

    leaderboard = sorted(data[chat_id].items(), key=lambda x: x[1]["points"], reverse=True)
    text = "🏆 *Таблиця лідерів:*\n\n"
    for i, (user_id, user_data) in enumerate(leaderboard[:10], 1):
        name = user_data.get("name", "Unknown")
        points = user_data.get("points", 0)
        text += f"{i}. {name} — {points} балів\n"

    await update.message.reply_markdown(text)
