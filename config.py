import os
import pytz

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {917781997}  # Множество для быстрой проверки
GROUP_CHAT_ID = -1002245200459

# --- Пути к файлам ---
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
SEASON_START_SNAPSHOT_FILE = os.path.join(DATA_DIR, "season_start.json")


# --- Игровые константы ---
ITEM_CATALOG = {
    "champion_crown": {"name": "👑Корона чемпіона", "description": "null"},
    "golden_penis": {"name": "👃Золотий пеніс", "description": "null"},
    "pink_dildo": {"name": "👅Рожевий ділдо", "description": "null"},
    "anal_ball": {"name": "⚾Анальний шар", "description": "null"},
    "birthday_hat": {"name": "🎉Святкова шапка", "description": "null"}
}

ITEM_REWARDS = {
    "gold": "golden_penis",
    "silver": "pink_dildo",
    "bronze": "anal_ball"
}

MEDAL_EMOJIS = {
    "gold": "🥇",
    "silver": "🥈",
    "bronze": "🥉"
}

# --- Настройки планировщика ---
TIMEZONE = pytz.timezone('Europe/Kyiv')
