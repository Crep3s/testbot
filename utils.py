from telegram import ReplyKeyboardMarkup
import config
import data_manager

def get_main_keyboard():
    buttons = [["/profile", "/inventory"], ["/season"], ["/leaderboard"]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def check_registered(user_id):
    data = data_manager.load_json(config.LEADERBOARD_FILE)
    return str(user_id) in data.get(str(config.GROUP_CHAT_ID), {})

def format_medals(medals):
    result = ""
    if medals.get("gold"): result += config.MEDAL_EMOJIS["gold"] * medals["gold"]
    if medals.get("silver"): result += config.MEDAL_EMOJIS["silver"] * medals["silver"]
    if medals.get("bronze"): result += config.MEDAL_EMOJIS["bronze"] * medals["bronze"]
    return result

def safe_username(name):
    # В будущем можно добавить экранирование для Markdown
    return name

def format_leaderboard(chat_data):
    sorted_users = sorted(chat_data.values(), key=lambda x: x["points"], reverse=True)
    lines = ["🏆 *Таблиця лідерів:*"]
    
    for i, user in enumerate(sorted_users, 1):
        points = user.get("points", 0)
        last = user.get("last_points")
        delta_str = ""

        if last is not None:
            delta = points - last
            if delta > 0: delta_str = f" (🔺+{delta})"
            elif delta < 0: delta_str = f" (🔻{delta})"

        name = user["name"]
        medals = format_medals(user.get("medals", {}))

        if points == 0:
            lines.append(f"\u200E{i}. {medals} *{name}* \u200E не має песюна")
        else:
            lines.append(f"\u200E{i}. {medals} *{name}* — \u200E {points} см{delta_str}")
    
    lines.append("\n#leaderboard")
    return "\n".join(lines)
