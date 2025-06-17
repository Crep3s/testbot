import logging
import json
import os
import random
import asyncio
import aiohttp
import nest_asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputFile
from telegram.constants import ChatType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from datetime import datetime, timezone
import zipfile
import io

nest_asyncio.apply()

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

LEADERBOARD_FILE = os.path.join(DATA_DIR, "leaderboard.json")
PREVIOUS_LEADERBOARD_FILE = os.path.join(DATA_DIR, "previous_leaderboard.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
SEASONS_FILE = os.path.join(DATA_DIR, "seasons.json")
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.json")
LIFETIME_FILE = os.path.join(DATA_DIR, "lifetime.json")
LAST_ACTIVE_FILE = os.path.join(DATA_DIR, "last_active.json")
SEASON_CACHE_FILE = os.path.join(DATA_DIR, "season_cache.json")

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = {917781997}
GROUP_CHAT_ID = -1001214853632

ITEM_CATALOG = {
    "champion_crown": {
        "name": "👑Корона чемпіона",
        "description": "null",
    },
    "golden_penis": {
        "name": "👃Золотий пеніс",
        "description": "null",
    },
    "pink_dildo": {
        "name": "👅Рожевий ділдо",
        "description": "null",
    },
    "anal_ball": {
        "name": "⚾Анальний шар",
        "description": "null",
    },
    "birthday_hat": {
        "name": "🎉Святкова шапка",
        "description": "null",
    }
}

ITEM_REWARDS = {
    "gold": "golden_penis",
    "silver": "pink_dildo",
    "bronze": "anal_ball"
}

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE or update.effective_user.id not in ADMIN_IDS:
        return
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fname in os.listdir(DATA_DIR):
            if fname.endswith(".json"):
                zipf.write(os.path.join(DATA_DIR, fname), arcname=fname)
    buffer.seek(0)

    # Надсилання ZIP-файлу
    await update.message.reply_document(
        document=InputFile(buffer, filename="backup.json.zip"),
        caption="🗃️ бекап"
    )

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE or update.effective_user.id not in ADMIN_IDS:
        return

    if not update.message.document or not update.message.document.file_name.endswith(".zip"):
        await update.message.reply_text("📎 Надішліть ZIP-файл із бекапом.")
        return

    file = await update.message.document.get_file()
    zip_path = os.path.join(DATA_DIR, "restore_temp.zip")
    await file.download_to_drive(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(DATA_DIR)
        await update.message.reply_text("✅ Бекап відновлено успішно.")
    except zipfile.BadZipFile:
        await update.message.reply_text("❌ Помилка: файл не є дійсним ZIP.")

def save_season_snapshot():
    leaderboard = load_json(LEADERBOARD_FILE)
    lifetime = load_json(LIFETIME_FILE)
    seasons = load_json(SEASONS_FILE)
    season_start = load_json("season_start.json")

    for chat_id in leaderboard.keys():
        current_season = seasons.get(chat_id, {}).get("current_season", 0) + 1
        season_snapshot = {}

        for user_id in leaderboard[chat_id].keys():
            lt = lifetime.get(user_id, {
                "total_tasks_completed": 0,
                "days_played": 0,
                "streak_max": 0
            })

            season_snapshot[user_id] = {
                "total_tasks_completed": lt.get("total_tasks_completed", 0),
                "days_played": lt.get("days_played", 0),
                "streak_max": lt.get("streak_max", 0)
            }

        season_start[chat_id] = {
            "season": current_season,
            "snapshot": season_snapshot
        }

    save_json(season_start, "season_start.json")


def calculate_deltas(current, previous):
    for chat_id in current:
        for user_id, user_data in current[chat_id].items():
            prev_points = previous.get(chat_id, {}).get(user_id, {}).get("points", 0)
            delta = user_data["points"] - prev_points
            user_data["last_delta"] = delta
    return current

def update_lifetime_stats(user_id, key, increment=1):
    lifetime = load_json(LIFETIME_FILE)
    user = lifetime.setdefault(user_id, {
        "tasks": 0, "": 0, "seasons": [],
        "days_played": 0, "current_streak": 0, "streak_max": 0, "reply_count": 0, "failed_tasks": -1, "total_tasks_completed": 0
    })

    if key == "date_check":
        from datetime import date, timedelta
        today = date.today().isoformat()
        last_active = load_json(LAST_ACTIVE_FILE)
        last = last_active.get(user_id)
        if last != today:
            user["days_played"] += 1
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last == yesterday:
                user["current_streak"] += 1
            else:
                user["current_streak"] = 1
            user["streak_max"] = max(user["streak_max"], user["current_streak"])
            last_active[user_id] = today
            save_json(last_active, LAST_ACTIVE_FILE)
    elif key == "keywords_used":
        pass
    else:
        user[key] = user.get(key, 0) + increment

    save_json(lifetime, LIFETIME_FILE)

medal_emojis = {
    "gold": "🥇",
    "silver": "🥈",
    "bronze": "🥉"
}

def format_medals(medals):
    result = ""
    if medals.get("gold"): result += "🥇" * medals["gold"]
    if medals.get("silver"): result += "🥈" * medals["silver"]
    if medals.get("bronze"): result += "🥉" * medals["bronze"]
    return result

def safe_username(name):
    return name

def get_main_keyboard():
    buttons = [
        ["/profile", "/inventory"],
        ["/season"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def check_registered(user_id):
    data = load_json(LEADERBOARD_FILE)
    return str(user_id) in data.get(str(GROUP_CHAT_ID), {})

def format_leaderboard(chat_data):
    sorted_users = sorted(chat_data.values(), key=lambda x: x["points"], reverse=True)
    lines = ["🏆 *Таблиця лідерів:*"]
    
    for i, user in enumerate(sorted_users, 1):
        points = user.get("points", 0)
        last = user.get("last_points")
        delta_str = ""

        if last is not None:
            delta = points - last
            if delta > 0:
                delta_str = f" (🔺+{delta})"
            elif delta < 0:
                delta_str = f" (🔻{delta})"

        name = user["name"]
        medals = format_medals(user.get("medals", {}))

        if points == 0:
            lines.append('\u200E' + f"{i}. {medals} *{name}* \u200E не має песюна")
        else:
            lines.append('\u200E' + f"{i}. {medals} *{name}* — \u200E {points} см{delta_str}")
    
    lines.append("\n#leaderboard")
    return "\n".join(lines)

async def add_reaction_to_message(bot_token, chat_id, message_id, emoji, context):
    url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if not response.ok:
                    text = await response.text()
                    await context.bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=message_id)
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=message_id)

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Ця команда працює тільки в групах.")
        return
    
    user = update.effective_user
    chat_id = str(update.effective_chat.id)
    data = load_json(LEADERBOARD_FILE)

    if chat_id not in data:
        data[chat_id] = {}

    user_id = str(user.id)
    if user_id in data[chat_id]:
        await update.message.reply_text(f"\u200E{user.full_name}, ти вже в грі.")
        return

    # Завантаження lifetime
    lifetime = load_json(LIFETIME_FILE)
    user_lifetime = lifetime.get(user_id, {})
    medals = user_lifetime.get("medals", {})

    # Завантаження кешу сезону
    season_cache = load_json(SEASON_CACHE_FILE)
    cached_points = season_cache.get(chat_id, {}).pop(user_id, None)
    save_json(season_cache, SEASON_CACHE_FILE)

    points = cached_points if cached_points is not None else 0

    data[chat_id][user_id] = {
        "name": user.full_name,
        "points": points,
        "last_delta": 0,
        "medals": medals
    }

    save_json(data, LEADERBOARD_FILE)
    await update.message.reply_text(f"\u200E{user.full_name} приєднався до гри! Песюн: {points} см")

async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Ця команда працює тільки в групі.")
        return

    user = update.effective_user
    chat_id = str(update.effective_chat.id)
    data = load_json(LEADERBOARD_FILE)
    user_id = str(user.id)

    if chat_id in data and user_id in data[chat_id]:
        save_json(data, PREVIOUS_LEADERBOARD_FILE)
        leaderboard_user = data[chat_id][user_id]

        # Загружаем lifetime
        lifetime = load_json(LIFETIME_FILE)
        user_lifetime = lifetime.setdefault(user_id, {
            "name": user.full_name,
            "tasks": 0, "": 0, "seasons": [],
            "days_played": 0, "current_streak": 0, "streak_max": 0,
            "reply_count": 0, "failed_tasks": 0, "total_tasks_completed": 0,
            "medals": {"gold": 0, "silver": 0, "bronze": 0}
        })

        # Обновляем имя (на всякий случай)
        user_lifetime["name"] = user.full_name

        user_lifetime.setdefault("total_points", 0)
        user_lifetime["total_points"] += leaderboard_user.get("points", 0)

        # Обновляем медали из лидерборда
        lb_medals = leaderboard_user.get("medals", {})
        lifetime_medals = user_lifetime.setdefault("medals", {"gold": 0, "silver": 0, "bronze": 0})
        for medal, count in lb_medals.items():
            lifetime_medals[medal] = lifetime_medals.get(medal, 0) + count

        # Сохраняем изменения
        lifetime[user_id] = user_lifetime
        save_json(lifetime, LIFETIME_FILE)

        # Удаляем из лидерборда
        del data[chat_id][user_id]
        season_cache = load_json(SEASON_CACHE_FILE)
        season_cache.setdefault(chat_id, {})[user_id] = leaderboard_user.get("points", 0)
        save_json(season_cache, SEASON_CACHE_FILE)
        save_json(data, LEADERBOARD_FILE)

        await update.message.reply_text(f"\u200E{user.full_name} вийшов з гри.")

    else:
        await update.message.reply_text("Тебе немає в грі.")


async def update_points():
    logging.info("🔁 Оновлення очок розпочато")
    data = load_json(LEADERBOARD_FILE)
    previous = load_json(PREVIOUS_LEADERBOARD_FILE)

    updated = False

    for chat_id in data:
        for user_id in data[chat_id]:
            user = data[chat_id][user_id]
            prev_points = user.get("points", 0)
            delta = random.randint(-5, 10)
            user["last_points"] = prev_points
            user["points"] = max(0, prev_points + delta)
            user["last_delta"] = delta
            previous.setdefault(chat_id, {})[user_id] = {"points": prev_points}
            updated = True

    if updated:
        save_json(data, LEADERBOARD_FILE)
        save_json(previous, PREVIOUS_LEADERBOARD_FILE)
        logging.info("✅ Очки оновлено")

def update_season_file(chat_id, top_players):
    seasons = load_json(SEASONS_FILE)

    if chat_id not in seasons:
        seasons[chat_id] = {
            "current_season": 0,
            "history": []
        }

    current_season = seasons[chat_id]["current_season"] + 1

    season_data = {
        "season": current_season,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "winners": []
    }

    for i, (user_id, user) in enumerate(top_players):
        medal = ["gold", "silver", "bronze"][i]
        season_data["winners"].append({
            "user_id": user_id,
            "name": user.get("name"),
            "medal": medal
        })

    seasons[chat_id]["current_season"] = current_season
    seasons[chat_id]["history"].append(season_data)

    save_json(seasons, SEASONS_FILE)

async def reset_season():
    leaderboard = load_json(LEADERBOARD_FILE)
    seasons = load_json(SEASONS_FILE)
    inventory = load_json(INVENTORY_FILE)
    lifetime = load_json(LIFETIME_FILE)
    season_start = load_json("season_start.json")

    for chat_id, board in leaderboard.items():
        # Поточний номер сезону
        if chat_id not in seasons:
            seasons[chat_id] = {"current_season": 0, "history": []}
        current = seasons[chat_id]["current_season"] + 1

        # Створюємо повну таблицю очок за сезон
        scores = {
            uid: {
                "points": user.get("points", 0),
                "name": user.get("name", "Невідомий")
            }
            for uid, user in sorted(board.items(), key=lambda x: x[1]["points"], reverse=True)
        }

        # Підготовка сезонного об'єкта
        season_data = {
            "season": current,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "winners": [],
            "scores": scores
        }

        # Формуємо топ-3
        top = list(scores.items())[:3]

        # Створення тексту для повідомлення
        text = f"🏁 Сезон {current} завершено!\n\nТоп-3 песюна:\n"

        snapshot = season_start.get(chat_id, {}).get("snapshot", {})

        for i, (uid, user_info) in enumerate(top):
            medal = ["gold", "silver", "bronze"][i]
            user = board.get(uid)
            if not user:
                continue  # захист від неповних даних

            # Нагородження медаллю
            if "medals" not in user:
                user["medals"] = {}
            user["medals"][medal] = user["medals"].get(medal, 0) + 1

            # Додавання предмета
            item_id = ITEM_REWARDS[medal]
            inventory.setdefault(uid, []).append(item_id)
            item = ITEM_CATALOG[item_id]

            # Статистика гравця
            lt = lifetime.setdefault(uid, {
                "total_tasks_completed": 0,
                "days_played": 0,
                "streak_max": 0
            })
            prev = snapshot.get(str(uid), {
                "total_tasks_completed": 0,
                "days_played": 0,
                "streak_max": 0
            })

            stats = {
                "total_tasks_completed": lt.get("total_tasks_completed", 0) - prev.get("total_tasks_completed", 0),
                "days_played": lt.get("days_played", 0) - prev.get("days_played", 0),
                "streak_max": lt.get("streak_max", 0)
            }

            # Додаємо до історії сезону
            season_data["winners"].append({
                "user_id": uid,
                "name": user.get("name", "Невідомий"),
                "medal": medal,
                "stats": stats,
                "points": user.get("points", 0)
            })

            # Формування повідомлення
            emoji = medal_emojis.get(medal, "")
            stats_summary = (
                f"  🧾 Завдань: {stats['total_tasks_completed']} | "
                f"Днів активності: {stats['days_played']} | "
                f"Серія: {stats['streak_max']} днів"
            )
            points = user.get("points", 0)
            text += f"\u200E{emoji} \u200E{safe_username(user['name'])} — {points} см. Нагорода: {item['name']}\n{stats_summary}\n\n"
    
        # Додаємо очки сезону до lifetime
        for uid, user in board.items():
            lifetime.setdefault(uid, {}).setdefault("total_points", 0)
            lifetime[uid]["total_points"] += user.get("points", 0)

        # Обнуляємо очки сезону
        for user in board.values():
            user["points"] = 0
            user["last_delta"] = 0
            user["last_points"] = 0

        # Збереження даних
        seasons[chat_id]["current_season"] = current
        seasons[chat_id]["history"].append(season_data)

        await send_group_message(text)

    # Фінальне збереження всіх файлів
    save_json(leaderboard, LEADERBOARD_FILE)
    save_json(seasons, SEASONS_FILE)
    save_json(inventory, INVENTORY_FILE)
    save_json(lifetime, LIFETIME_FILE)

async def send_group_message(text):
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=text)

# Админ команда выдачи предметов
async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Сасі.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Використання: /additem <user_id> <item_id>")
        return

    user_id, item_id = context.args[0], context.args[1]
    if item_id not in ITEM_CATALOG:
        await update.message.reply_text("❌ Такого предмета не існує.")
        return
    leaderboard = load_json(LEADERBOARD_FILE)
    inventory = load_json(INVENTORY_FILE)
    inventory.setdefault(user_id, []).append(item_id)
    save_json(inventory, INVENTORY_FILE)
    chat_id = str(GROUP_CHAT_ID)
    user_data = leaderboard.get(chat_id, {}).get(user_id)
    if not user_data:
        await update.message.reply_text("Гравець не знайдений у таблиці.")
        return
    name = safe_username(user_data.get("name", "Гравець"))
    item_name = ITEM_CATALOG[item_id]["name"]
    await update.message.reply_text(f"\u200E✅ Предмет {item_name} видано користувачу \u200E{name}")


# Заглушки игровых функций (пока сокращаю — можно будет вернуть позже):
async def dummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ Ця команда поки що недоступна.")

async def send_daily_task(app):
    leaderboard = load_json(LEADERBOARD_FILE)
    tasks = load_json(TASKS_FILE)
    previous = load_json(PREVIOUS_LEADERBOARD_FILE)
    progress = load_json(PROGRESS_FILE)
    leaderboard = calculate_deltas(leaderboard, previous)
    save_json(leaderboard, PREVIOUS_LEADERBOARD_FILE)

    task_list = [
        {"description": "Відправити 3 повідомлення", "type": "messages", "goal": 3, "bonus": 10},
        {"description": "Відправити голосове повідомлення тривалістю не менше 10 секунд", "type": "voice", "goal": 10, "bonus": 15},
        {"description": "Відправити відеоповідомлення тривалістю не менше 5 секунд", "type": "video_note", "goal": 5, "bonus": 15},
        {"description": "Відправити 2 медіафайли", "type": "media", "goal": 2, "bonus": 10},
        {"description": "Відправити стікер", "type": "sticker", "goal": 1, "bonus": 7},
        {"description": "Надіслати повідомлення з емодзі 😈", "type": "emoji", "goal": 1, "emoji": "😈", "bonus": 7},
        {"description": "Надіслати повідомлення з емодзі 🥵", "type": "emoji", "goal": 1, "emoji": "🥵", "bonus": 7},
        {"description": "Надіслати повідомлення з емодзі 🤯", "type": "emoji", "goal": 1, "emoji": "🤯", "bonus": 7},
        {"description": "Відправити хоча б одне фото", "type": "photo", "goal": 1, "bonus": 10},
        {"description": "Надіслати відео", "type": "video", "goal": 1, "bonus": 15},
        {"description": "Надіслати GIF", "type": "animation", "goal": 1, "bonus": 12},
        {"description": "Задати 2 запитання", "type": "question", "goal": 2, "bonus": 12},
        {"description": "Написати повідомлення, яке містить слово «смегма»", "type": "keyword", "subtype": "смегма", "goal": 1, "bonus": 7},
        {"description": "Надіслати повідомлення довжиною понад 30 символів", "type": "long_message", "goal": 1, "bonus": 10},
        {"description": "Надіслати відповідь на чуже повідомлення", "type": "reply", "goal": 1, "bonus": 10},
        {"description": "Надіслати зображення з підписом", "type": "photo_with_caption", "goal": 1, "bonus": 15}
    ]

    for chat_id in leaderboard:
        task = random.choice(task_list)

        # Провалені завдання
        for user_id in leaderboard[chat_id]:
            key = f"{chat_id}:{user_id}"
            if progress.get(key, 0) < tasks.get(chat_id, {}).get("goal", 999):
                update_lifetime_stats(user_id, "failed_tasks")

        tasks[chat_id] = task

        # Очистити старий прогрес
        keys_to_delete = [k for k in progress if k.startswith(f"{chat_id}:")]
        for k in keys_to_delete:
            del progress[k]
        save_json(progress, PROGRESS_FILE)

        text = format_leaderboard(leaderboard[chat_id])
        text += f"\n\n🎯 *Завдання дня:*\n_{task['description']}_\nБонус: *{task['bonus']} см*"

        try:
            await app.bot.send_message(chat_id=int(chat_id), text=text, parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Не вдалося надіслати завдання в чат {chat_id}: {e}")

    save_json(tasks, TASKS_FILE)

async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return

    user_id = str(message.from_user.id)
    chat_id = str(message.chat_id)
    tasks = load_json(TASKS_FILE)
    progress = load_json(PROGRESS_FILE)
    leaderboard = load_json(LEADERBOARD_FILE)

    if chat_id not in tasks or user_id not in leaderboard.get(chat_id, {}):
        return

    task = tasks[chat_id]
    key = f"{chat_id}:{user_id}"
    current = progress.get(key, 0)
    completed_before = current >= task["goal"]
    update_lifetime_stats(user_id, "date_check") 
    if task["type"] == "messages":
        current += 1
    elif task["type"] == "voice" and message.voice:
        if message.voice.duration >= task["goal"]:
            current = task["goal"]
    elif task["type"] == "video_note" and message.video_note:
        if message.video_note.duration >= task["goal"]:
            current = task["goal"]
    elif task["type"] == "media" and (message.photo or message.video or message.document):
        current += 1
    elif task["type"] == "sticker" and message.sticker:
        current += 1
    elif task["type"] == "emoji" and message.text and task.get("emoji") in message.text:
        current += 1
    elif task["type"] == "photo" and message.photo:
        current = task["goal"]
    elif task["type"] == "video" and message.video:
        current += 1
    elif task["type"] == "animation" and message.animation:
        current = task["goal"]
    elif task["type"] == "question" and message.text and "?" in message.text:
        current += 1
    elif task["type"] == "keyword" and message.text:
        if task.get("subtype") in message.text.lower():
            current = task["goal"]
    elif task["type"] == "long_message" and message.text:
        if len(message.text) > 30:
            current = task["goal"]
    elif task["type"] == "reply" and message.reply_to_message:
        current += 1
    elif task["type"] == "photo_with_caption" and message.photo and message.caption:
        current = task["goal"]

    progress[key] = min(current, task["goal"])
    save_json(progress, PROGRESS_FILE)

    if not completed_before and progress[key] >= task["goal"]:
        leaderboard[chat_id][user_id]["points"] += task.get("bonus", 0)
        save_json(leaderboard, LEADERBOARD_FILE)
        update_lifetime_stats(user_id, "total_tasks_completed")
        await add_reaction_to_message(BOT_TOKEN, message.chat_id, message.message_id, "👍", context)


async def modify_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Сасі.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Використання: /addpoints <user_id> <кількість>")
        return

    user_id, amount = context.args
    try:
        amount = int(amount)
    except ValueError:
        await update.message.reply_text("Не число.")
        return

    chat_id = str(update.effective_chat.id)
    leaderboard = load_json(LEADERBOARD_FILE)

    if chat_id in leaderboard and user_id in leaderboard[chat_id]:
        user_data = leaderboard[chat_id][user_id]
        user_data["points"] += amount
        save_json(leaderboard, LEADERBOARD_FILE)

        name = safe_username(user_data.get("name", "Гравець"))
        new_total = user_data["points"]

        # Повідомлення в групу
        if amount > 0:
            msg = f"\u200E{name}, твій песюн виріс на {amount} см!"
        elif amount < 0:
            msg = f"\u200E{name}, твій песюн зменшився на {abs(amount)} см."
        else:
            msg = None

        if msg:
            await context.bot.send_message(chat_id=int(chat_id), text=msg)
    else:
        await update.message.reply_text("Гравець не знайдений у таблиці.")


async def admin_send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔️ У вас немає прав для цієї дії.")
        return

    context.user_data["awaiting_send_to_group"] = True
    await update.message.reply_text("✅ Відправте наступне повідомлення, щоб надіслати його в групу.")

# Обробник наступного повідомлення
async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    if not context.user_data.get("awaiting_send_to_group"):
        return  # ничего не делаем, если не ждем сообщение

    message = update.message
    try:
        # Сбросим флаг, чтобы больше не ждать
        context.user_data["awaiting_send_to_group"] = False

        if message.text:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=message.text,
                parse_mode='Markdown'
            )
        elif message.photo:
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=message.caption if message.caption else None,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❗️ Тип повідомлення не підтримується.")
            return

        await update.message.reply_text("✅ Повідомлення надіслано в групу.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка при надсиланні: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    await update.message.reply_text("Ласкаво просимо до гри Найдовший песюн! Виберіть один із запропонованих варіантів для управління грою", reply_markup=get_main_keyboard())

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    user_id = str(update.effective_user.id)
    chat_id = str(GROUP_CHAT_ID)

    leaderboard = load_json(LEADERBOARD_FILE).get(chat_id, {})
    lifetime = load_json(LIFETIME_FILE).get(user_id, {})
    season_cache = load_json(SEASON_CACHE_FILE).get(chat_id, {})
    if user_id not in leaderboard:
        await update.message.reply_text("Ви ще не зареєстровані. Напишіть /join у групі.", reply_markup=get_main_keyboard())
        return
    in_game = user_id in leaderboard
    season_points = leaderboard.get(user_id, {}).get("points", 0) if in_game else 0
    total_past_points = lifetime.get("total_points", 0)
    total_points = total_past_points + season_points

    medals = format_medals(leaderboard.get(user_id, {}).get("medals", lifetime.get("medals", {})))

    text = (
        f"🙎‍♂️ Ваш профіль\n\n"
        f"{medals} {safe_username(update.effective_user.full_name)}\n"
        f"🔢 Усього сантиметрів: {total_points} см\n"
        f"✅ Завдань виконано: {lifetime.get('total_tasks_completed', 0)}\n"
        f"❌ Завдань пропущено: {lifetime.get('failed_tasks', 0)}\n"
        f"📅 Днів активності: {lifetime.get('days_played', 0)}\n"
        f"🔥 Серія: {lifetime.get('current_streak', 0)} (макс: {lifetime.get('streak_max', 0)})"
    )

    await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    user_id = str(update.effective_user.id)
    lb = load_json(LEADERBOARD_FILE).get(str(GROUP_CHAT_ID), {})
    if user_id not in lb:
        await update.message.reply_text("Ви ще не зареєстровані. Напишіть /join у групі.", reply_markup=get_main_keyboard())
        return

    inv = load_json(INVENTORY_FILE).get(user_id, [])
    if not inv:
        await update.message.reply_text("🎒 Ваш інвентар порожній.", reply_markup=get_main_keyboard())
        return
    text = "🎒 Ваш інвентар:\n"
    for item_id in inv:
        item = ITEM_CATALOG.get(item_id)
        if item:
            text += f"- {item['name']}: {item['description']}\n"
        else:
            text += f"- ❓ Невідомий предмет: {item_id}\n"
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

SEASON = range(1)

async def season_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    await update.message.reply_text("Введіть номер сезону:", reply_markup=ReplyKeyboardRemove())
    return SEASON

async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num = update.message.text.strip()
    if not num.isdigit() or int(num) <= 0:
        await update.message.reply_text("Некоректний номер.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    num = int(num)
    user_id = str(update.effective_user.id)
    chat_id = str(GROUP_CHAT_ID)

    # Загружаем файл сезонов
    seasons_data = load_json(SEASONS_FILE).get(chat_id, {})
    history = seasons_data.get("history", [])

    if not history:
        await update.message.reply_text("Історія сезонів порожня.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # Ищем нужный сезон
    matched_season = next((s for s in history if s.get("season") == num), None)
    if not matched_season:
        await update.message.reply_text("Сезон не знайдено.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    text = f"🏁 Сезон {num}\n\n"
    text += "Топ-3 песюна:\n"

    for winner in matched_season["winners"]:
        w_id = winner["user_id"]
        name = safe_username(winner["name"])
        medal = winner["medal"]
        emoji = medal_emojis.get(medal, "")
        item_id = ITEM_REWARDS.get(medal, "🎁")
        item = ITEM_CATALOG.get(item_id, {"name": "Невідомий приз"})

        # Берем статистику за сезон
        stats = winner.get("stats", {})
        tasks_completed = stats.get("total_tasks_completed", 0)
        days_played = stats.get("days_played", 0)
        streak_max = stats.get("streak_max", 0)

        stats_summary = (
            f"  🧾 Завдань: {tasks_completed} | "
            f"Днів активності: {days_played} | "
            f"Серія: {streak_max} днів"
        )

        points = winner.get("points", 0)
        text += f"\u200E{emoji} {name} — {points} см. Нагорода: {item['name']}\n{stats_summary}\n\n"


    # Показати місце користувача, якщо він не в топ-3
    scores = matched_season.get("scores", {})
    if scores and user_id in scores:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]["points"], reverse=True)
        for idx, (uid, user_data) in enumerate(sorted_scores, start=1):
            if uid == user_id:
                place_points = user_data.get("points", 0)
                text += f"\n📌 Ви зайняли {idx}-е місце з песюном {place_points} см."
                break

                    
    ended = matched_season.get("ended_at")
    if ended:
        try:
            ended_fmt = datetime.fromisoformat(ended).strftime("%d.%m.%Y %H:%M")
            text += f"\n📅 Завершено: {ended_fmt}"
        except Exception:
            pass

    await update.message.reply_text(text, reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не встановлено")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("inventory", inventory_command))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("addpoints", modify_points))
    app.add_handler(CommandHandler("additem", add_item))
    app.add_handler(CommandHandler("send", admin_send_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, restore_command))

    conv = ConversationHandler(
        entry_points=[CommandHandler("season", season_entry)],
        states={SEASON: [MessageHandler(filters.TEXT, season_command)]},
        fallbacks=[]
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.ALL, admin_message_handler))
    app.add_handler(MessageHandler(filters.ALL, track_activity))
    kyiv_tz = pytz.timezone('Europe/Kyiv')
    scheduler = AsyncIOScheduler(timezone=kyiv_tz)
    scheduler.add_job(reset_season, trigger='cron', day=1, hour=0, minute=0)
    scheduler.add_job(save_season_snapshot, trigger='cron', day=1, hour=0, minute=1)
    scheduler.add_job(update_points, trigger='cron', hour=7, minute=59)
    scheduler.add_job(send_daily_task, trigger='cron', hour=8, minute=0, args=[app])
    scheduler.start()

    print("Бот запущено")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
