import logging
import random
from datetime import datetime, timezone
import data_manager
import config
import utils
import game_logic

async def update_points():
    logging.info("🔁 Оновлення очок розпочато")
    data = data_manager.load_json(config.LEADERBOARD_FILE)
    previous = data_manager.load_json(config.PREVIOUS_LEADERBOARD_FILE)
    
    for chat_id in data:
        for user_id, user in data[chat_id].items():
            prev_points = user.get("points", 0)
            delta = random.randint(-5, 10)
            user["last_points"] = prev_points
            user["points"] = max(0, prev_points + delta)
            user["last_delta"] = delta
            previous.setdefault(chat_id, {})[user_id] = {"points": prev_points}

    data_manager.save_json(data, config.LEADERBOARD_FILE)
    data_manager.save_json(previous, config.PREVIOUS_LEADERBOARD_FILE)
    logging.info("✅ Очки оновлено")


async def send_daily_task(app):
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)
    tasks = data_manager.load_json(config.TASKS_FILE)
    progress = data_manager.load_json(config.PROGRESS_FILE)
    
    task_list = [
        {"description": "Відправити 3 повідомлення", "type": "messages", "goal": 3, "bonus": 10},
        {"description": "Відправити голосове повідомлення тривалістю не менше 5 секунд", "type": "voice", "goal": 5, "bonus": 15},
        {"description": "Відправити відеоповідомлення тривалістю не менше 5 секунд", "type": "video_note", "goal": 5, "bonus": 15},
        {"description": "Відправити будь який медіафайл", "type": "media", "goal": 1, "bonus": 10},
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
        {"description": "Надіслати зображення з підписом", "type": "photo_with_caption", "goal": 1, "bonus": 15},
        {"description": "Поділитися геолокацією (будь-якою)", "type": "location", "goal": 1, "bonus": 10}
    ]

    for chat_id_str in leaderboard:
        chat_id = str(chat_id_str)
        previous_task_type = tasks.get(chat_id, {}).get("type")
        available_tasks = [t for t in task_list if t["type"] != previous_task_type]
        task = random.choice(available_tasks or task_list)  # якщо всі були одного типу

        # Проваленные задачи
        for user_id in leaderboard[chat_id]:
            key = f"{chat_id}:{user_id}"
            if progress.get(key, 0) < tasks.get(chat_id, {}).get("goal", 999):
                game_logic.update_lifetime_stats(user_id, "failed_tasks")

        tasks[chat_id] = task
        tasks[chat_id]["last_type"] = task["type"]
        # Очистка прогресса
        keys_to_delete = [k for k in progress if k.startswith(f"{chat_id}:")]
        for k in keys_to_delete: del progress[k]
        
        data_manager.save_json(progress, config.PROGRESS_FILE)
        data_manager.save_json(tasks, config.TASKS_FILE)
        
        leaderboard_text = utils.format_leaderboard(leaderboard[chat_id])
        task_text = f"\n\n🎯 *Завдання дня:*\n_{task['description']}_\nБонус: *{task['bonus']} см*"
        try:
            await app.bot.send_message(chat_id=int(chat_id), text=leaderboard_text + task_text, parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Не вдалося надіслати завдання в чат {chat_id}: {e}")

async def reset_season(app):
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)
    seasons = data_manager.load_json(config.SEASONS_FILE)
    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    season_start = data_manager.load_json(config.SEASON_START_SNAPSHOT_FILE)

    for chat_id_str, board in leaderboard.items():
        chat_id = str(chat_id_str)
        if chat_id not in seasons:
            seasons[chat_id] = {
                "current_season": 0,
                "history": []
            }

        current_season_num = seasons[chat_id]["current_season"] + 1
        scores = {uid: {"points": u.get("points", 0), "name": u.get("name", "Невідомий")} for uid, u in board.items()}
        sorted_scores = sorted(scores.items(), key=lambda item: item[1]["points"], reverse=True)
        
        season_data = {
            "season": current_season_num,
            "ended_at": datetime.now(config.TIMEZONE).isoformat(),
            "winners": [],
            "scores": scores
        }

        text = f"🏁 Сезон {current_season_num} завершено!\n\nТоп-3 песюна:\n"
        top_players = sorted_scores[:3]
        snapshot = season_start.get(chat_id, {}).get("snapshot", {})
        medals = ["gold", "silver", "bronze"]

        for i, (uid, user_info) in enumerate(top_players):
            reward = config.DIAMOND_REWARDS[i]
            medal = medals[i]
            user = board.get(uid)
            if not user: continue

            # Медалі (як до цього)
            lifetime.setdefault(uid, {}).setdefault("medals", {})
            lifetime[uid]["medals"][medal] = lifetime[uid]["medals"].get(medal, 0) + 1

            # Додати алмази
            game_logic.add_diamonds(uid, reward)

            # Підрахунок статистики сезону
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

            season_data["winners"].append({
                "user_id": uid,
                "name": user.get("name", "Невідомий"),
                "medal": medal,
                "stats": stats,
                "points": user.get("points", 0)
            })

            emoji = config.MEDAL_EMOJIS.get(medal, "")
            points = user.get("points", 0)
            stats_summary = (
                f"Виконаних завдань: {stats.get('total_tasks_completed', 0)}\n"
                f"Днів активності: {stats.get('days_played', 0)}\n"
                f"Серія: {stats.get('streak_max', 0)} днів"
            )
            text += f"\u200E{emoji} \u200E{user['name']} — \u200E{points} см. Нагорода: 💎 {reward} алмазів\n{stats_summary}\n\n"

        # Зберігаємо загальні очки
        for uid, user in board.items():
            lifetime.setdefault(uid, {}).setdefault("total_points", 0)
            lifetime[uid]["total_points"] += user.get("points", 0)

        # Обнулення
        for user in board.values():
            user["points"] = 0
            user["last_delta"] = 0
            user["last_points"] = 0

        seasons[chat_id]["current_season"] = current_season_num
        seasons[chat_id]["history"].append(season_data)

        await app.bot.send_message(chat_id=int(chat_id), text=text)

    # Очищення кешу
    season_cache = data_manager.load_json(config.SEASON_CACHE_FILE)
    for chat_id_str in leaderboard.keys():
        chat_id = str(chat_id_str)
        if chat_id in season_cache:
            for uid in list(season_cache[chat_id].keys()):
                if uid not in leaderboard[chat_id]:
                    del season_cache[chat_id][uid]

    data_manager.save_json(season_cache, config.SEASON_CACHE_FILE)
    data_manager.save_json(leaderboard, config.LEADERBOARD_FILE)
    data_manager.save_json(seasons, config.SEASONS_FILE)
    data_manager.save_json(lifetime, config.LIFETIME_FILE)
