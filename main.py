import logging
import asyncio
import nest_asyncio
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import game_logic
import scheduler_tasks
from handlers import user_handlers, admin_handlers, general_handlers

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не встановлено в конфігурації!")

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("season", user_handlers.season_entry)],
        states={
            user_handlers.SEASON_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.season_command)]
        },
        fallbacks=[]
    )

    # Пользовательские команды
    app.add_handler(CommandHandler("start", user_handlers.start))
    app.add_handler(CommandHandler("profile", user_handlers.profile))
    app.add_handler(CommandHandler("inventory", user_handlers.inventory_command))
    app.add_handler(CommandHandler("leaderboard", user_handlers.show_leaderboard_private))
    app.add_handler(CommandHandler("join", user_handlers.join))
    app.add_handler(CommandHandler("leave", user_handlers.leave))
    app.add_handler(CommandHandler("version", user_handlers.version_command))
    app.add_handler(conv_handler)
    
    # Админские команды
    app.add_handler(CommandHandler("addpoints", admin_handlers.modify_points))
    app.add_handler(CommandHandler("additem", admin_handlers.add_item))
    app.add_handler(CommandHandler("adddiamonds", admin_handlers.grant_diamonds))
    app.add_handler(CommandHandler("send", admin_handlers.admin_send_command))
    app.add_handler(CommandHandler("backup", admin_handlers.backup_command))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, admin_handlers.restore_command))

    # Общие обработчики
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, admin_handlers.admin_message_handler))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.SUPERGROUP, general_handlers.track_activity))

    # --- Настройка планировщика ---
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(scheduler_tasks.reset_season, 'interval', seconds=175, args=[app])
    scheduler.add_job(game_logic.save_season_snapshot, 'interval', seconds=177)
    scheduler.add_job(scheduler_tasks.update_points, 'interval', seconds=59)
    scheduler.add_job(scheduler_tasks.send_daily_task, 'interval', seconds=60, args=[app])

    scheduler.start()
    logging.info("🎉 Бот запущен!")

    # Запускаем бота
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
