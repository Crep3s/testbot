import random
from datetime import datetime, timezone, date, timedelta
import data_manager
import config

def update_lifetime_stats(user_id, key, increment=1):
    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    user = lifetime.setdefault(str(user_id), {
        "tasks": 0,
        "seasons": [],
        "days_played": 0,
        "current_streak": 0,
        "streak_max": 0,
        "reply_count": 0,
        "failed_tasks": 0,
        "total_tasks_completed": 0,
        "diamonds": 0,
        "total_diamonds": 0
    })

    if key == "date_check":
        today = date.today().isoformat()
        last_active = data_manager.load_json(config.LAST_ACTIVE_FILE)
        last_played = last_active.get(str(user_id))
        if last_played != today:
            user["days_played"] += 1
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            user["current_streak"] = user["current_streak"] + 1 if last_played == yesterday else 1
            user["streak_max"] = max(user["streak_max"], user["current_streak"])
            last_active[str(user_id)] = today
            data_manager.save_json(last_active, config.LAST_ACTIVE_FILE)
    else:
        user[key] = user.get(key, 0) + increment

    data_manager.save_json(lifetime, config.LIFETIME_FILE)


def add_diamonds(user_id, amount, lifetime):
    user = lifetime.setdefault(str(user_id), {
        "diamonds": 0,
        "total_diamonds": 0
    })
    user["diamonds"] = user.get("diamonds", 0) + amount
    user["total_diamonds"] = user.get("total_diamonds", 0) + amount



def calculate_deltas(current, previous):
    for chat_id in current:
        for user_id, user_data in current[chat_id].items():
            prev_points = previous.get(chat_id, {}).get(user_id, {}).get("points", 0)
            delta = user_data["points"] - prev_points
            user_data["last_delta"] = delta
    return current

def save_season_snapshot():
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)
    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    seasons = data_manager.load_json(config.SEASONS_FILE)
    season_start = {}

    for chat_id_str in leaderboard.keys():
        chat_id = str(chat_id_str)
        current_season = seasons.get(chat_id, {}).get("current_season", 0) + 1
        season_snapshot = {}

        for user_id_str in leaderboard[chat_id].keys():
            user_id = str(user_id_str)
            lt = lifetime.get(user_id, {})
            season_snapshot[user_id] = {
                "total_tasks_completed": lt.get("total_tasks_completed", 0),
                "days_played": lt.get("days_played", 0),
                "streak_max": lt.get("streak_max", 0)
            }
        
        season_start[chat_id] = {
            "season": current_season,
            "snapshot": season_snapshot
        }
    
    data_manager.save_json(season_start, config.SEASON_START_SNAPSHOT_FILE)
