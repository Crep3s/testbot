from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from game_logic import add_diamonds
import config
import data_manager
import utils

async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS: return
    if len(context.args) < 2:
        await update.message.reply_text("Використання: /additem <user_id> <item_id>")
        return

    user_id, item_id = context.args[0], context.args[1]
    if item_id not in config.ITEM_CATALOG:
        await update.message.reply_text("❌ Такого предмета не існує.")
        return
    
    inventory = data_manager.load_json(config.INVENTORY_FILE)
    inventory.setdefault(user_id, []).append(item_id)
    data_manager.save_json(inventory, config.INVENTORY_FILE)
    
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)
    user_data = leaderboard.get(str(config.GROUP_CHAT_ID), {}).get(user_id)
    if not user_data:
        await update.message.reply_text("Гравець не знайдений, але предмет додано до інвентаря.")
        return
        
    name = utils.safe_username(user_data.get("name", "Гравець"))
    item_name = config.ITEM_CATALOG[item_id]["name"]
    await update.message.reply_text(f"\u200E✅ Предмет {item_name} видано користувачу \u200E{name}")

async def modify_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS: return
    if len(context.args) != 2:
        await update.message.reply_text("Використання: /addpoints <user_id> <кількість>")
        return

    user_id, amount_str = context.args
    try:
        amount = int(amount_str)
    except ValueError:
        await update.message.reply_text("Не число.")
        return

    chat_id = str(update.effective_chat.id) # Может быть группой
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)

    if chat_id in leaderboard and user_id in leaderboard[chat_id]:
        user_data = leaderboard[chat_id][user_id]
        user_data["points"] += amount
        data_manager.save_json(leaderboard, config.LEADERBOARD_FILE)
        name = utils.safe_username(user_data.get("name", "Гравець"))
        
        msg = ""
        if amount > 0: msg = f"\u200E{name}, твій песюн виріс на {amount} см!"
        elif amount < 0: msg = f"\u200E{name}, твій песюн зменшився на {abs(amount)} см."
        
        if msg: await context.bot.send_message(chat_id=int(chat_id), text=msg)
    else:
        await update.message.reply_text("Гравець не знайдений у таблиці цього чату.")

async def grant_diamonds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return

    if len(context.args) != 2:
        await update.message.reply_text("Використання: /adddiamonds <user_id> <кількість>")
        return

    user_id, amount_str = context.args
    try:
        amount = int(amount_str)
    except ValueError:
        await update.message.reply_text("❌ Неправильне число.")
        return

    if amount <= 0:
        await update.message.reply_text("❌ Кількість має бути позитивною.")
        return
    lifetime = data_manager.load_json(config.LIFETIME_FILE)
    chat_id = str(update.effective_chat.id)
    leaderboard = data_manager.load_json(config.LEADERBOARD_FILE)
    user_data = leaderboard[chat_id][user_id]
    name = utils.safe_username(user_data.get("name", "Гравець"))
    add_diamonds(user_id, amount, lifetime)
    data_manager.save_json(lifetime, config.LIFETIME_FILE)
    await update.message.reply_text(f"\u200E{name}, тобі нараховано 💎 {amount} алмазів")

async def admin_send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS: return
    context.user_data["awaiting_send_to_group"] = True
    await update.message.reply_text("✅ Відправте наступне повідомлення, щоб надіслати його в групу.")

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS or not context.user_data.get("awaiting_send_to_group"):
        return

    context.user_data["awaiting_send_to_group"] = False
    message = update.message
    try:
        if message.text:
            await context.bot.send_message(chat_id=config.GROUP_CHAT_ID, text=message.text, parse_mode='Markdown')
        elif message.photo:
            await context.bot.send_photo(chat_id=config.GROUP_CHAT_ID, photo=message.photo[-1].file_id, caption=message.caption, parse_mode='Markdown')
        else:
            await update.message.reply_text("❗️ Тип повідомлення не підтримується.")
            return
        await update.message.reply_text("✅ Повідомлення надіслано в групу.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка при надсиланні: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE or update.effective_user.id not in config.ADMIN_IDS: return
    
    zip_buffer = data_manager.create_backup_zip()
    await update.message.reply_document(
        document=InputFile(zip_buffer, filename="backup.json.zip"),
        caption="🗃️ бекап"
    )

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS: return
    if not update.message.document or not update.message.document.file_name.endswith(".zip"):
        await update.message.reply_text("📎 Надішліть ZIP-файл із бекапом.")
        return

    file = await update.message.document.get_file()
    success, message = await data_manager.restore_from_zip(file)
    await update.message.reply_text(message)
