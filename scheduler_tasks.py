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
    
    # ... (список task_list)
    task_list = [
        {"description": "Відправити 3 повідомлення", "type": "messages", "goal": 3, "bonus": 10},
        {"description": "Відправити голосове повідомлення тривалістю не менше 10 секунд", "type": "voice", "goal": 10, "bonus": 15},
        # ... и все остальные задачи
    ]

    for chat_id_str in leaderboard:
        chat_id = str(chat_id_str)
        task = random.choice(task_list)

        # Проваленные задачи
        for user_id in leaderboard[chat_id]:
            key = f"{chat_id}:{user_id}"
            if progress.get(key, 0) < tasks.get(chat_id, {}).get("goal", 999):
                game_logic.update_lifetime_stats(user_id, "failed_tasks")

        tasks[chat_id] = task
        
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
    inventory = data_manager.load_json(config.INVENTORY_FILE)
    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    season_start = data_manager.load_json(config.SEASON_START_SNAPSHOT_FILE)

    for chat_id_str, board in leaderboard.items():
        chat_id = str(chat_id_str)
        current_season_num = seasons.get(chat_id, {}).get("current_season", 0) + 1
        
        scores = {uid: {"points": u.get("points", 0), "name": u.get("name", "Невідомий")} for uid, u in board.items()}
        sorted_scores = sorted(scores.items(), key=lambda item: item[1]["points"], reverse=True)
        
        season_data = {"season": current_season_num, "ended_at": datetime.now(timezone.utc).isoformat(), "winners": [], "scores": scores}
        
        text = f"🏁 Сезон {current_season_num} завершено!\n\nТоп-3 песюна:\n"
        top_players = sorted_scores[:3]
        snapshot = season_start.get(chat_id, {}).get("snapshot", {})

        for i, (uid, user_info) in enumerate(top_players):
            medal = ["gold", "silver", "bronze"][i]
            user = board.get(uid)
            if not user: continue

            user.setdefault("medals", {})[medal] = user["medals"].get(medal, 0) + 1
            item_id = config.ITEM_REWARDS[medal]
            inventory.setdefault(uid, []).append(item_id)
            
            lt = lifetime.setdefault(uid, {})
            prev = snapshot.get(str(uid), {})
            stats = {
                "total_tasks_completed": lt.get("total_tasks_completed", 0) - prev.get("total_tasks_completed", 0),
                "days_played": lt.get("days_played", 0) - prev.get("days_played", 0),
                "streak_max": lt.get("streak_max", 0)
            }
            
            season_data["winners"].append({"user_id": uid, "name": user.get("name"), "medal": medal, "stats": stats, "points": user.get("points", 0)})
            
            # ... (Формирование текста сообщения, как в оригинале)

        # ... (Обновление lifetime, обнуление очков, сохранение данных)
        await app.bot.send_message(chat_id=int(chat_id), text=text)

    data_manager.save_json(leaderboard, config.LEADERBOARD_FILE)
    data_manager.save_json(seasons, config.SEASONS_FILE)
    data_manager.save_json(inventory, config.INVENTORY_FILE)
    data_manager.save_json(lifetime, config.LIFETIME_FILE)