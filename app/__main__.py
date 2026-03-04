import logging
import os
import time
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .bot import commands
from .bot.handlers import include_routers
from .bot.middlewares import register_middlewares
from .bot.utils.fsm_storage import SQLiteFSMStorage
from .bot.utils.sqlite import SQLiteDatabase
from .config import load_config
from .logger import setup_logger
from .migrations import run_migrations
from .migrations.redis_import import migrate_from_redis_if_needed


logger = logging.getLogger("support_bot.startup")


async def on_startup(
    bot: Bot,
    config,
    db: SQLiteDatabase,
    apscheduler: AsyncIOScheduler,
    dispatcher: Dispatcher,
) -> None:
    logger.info("connecting to sqlite: %s", config.sqlite.PATH)
    await db.connect()

    await migrate_from_redis_if_needed(config=config, db=db)

    logger.info("running migrations...")
    t = time.perf_counter()
    await run_migrations(config=config, bot=bot, db=db)
    logger.info("migrations done in %.2fs", time.perf_counter() - t)

    apscheduler.start()
    await commands.setup(bot, config)

    webhook_url = f"{config.bot.WEBHOOK_URL}/webhook"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=config.bot.WEBHOOK_SECRET,
        allowed_updates=dispatcher.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info("webhook registered: %s", webhook_url)


async def on_shutdown(
    bot: Bot,
    config,
    db: SQLiteDatabase,
    apscheduler: AsyncIOScheduler,
    dispatcher: Dispatcher,
) -> None:
    apscheduler.shutdown()
    await commands.delete(bot, config)
    await dispatcher.storage.close()
    await db.close()
    await bot.delete_webhook()
    await bot.session.close()


async def health_handler(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def main() -> None:
    setup_logger()
    config = load_config()

    logger.info("starting support-bot (webhook)")
    logger.info("dev_id: %s, group_id: %s", config.bot.DEV_ID, config.bot.GROUP_ID)

    base_dir = Path(__file__).resolve().parent.parent
    db_path = Path(config.sqlite.PATH)
    if not db_path.is_absolute():
        db_path = (base_dir / db_path).resolve()

    db = SQLiteDatabase(path=db_path)

    job_store = SQLAlchemyJobStore(url=f"sqlite:///{db_path.as_posix()}")
    apscheduler = AsyncIOScheduler(jobstores={"default": job_store})

    storage = SQLiteFSMStorage(db)

    bot = Bot(
        token=config.bot.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(
        apscheduler=apscheduler,
        storage=storage,
        config=config,
        bot=bot,
        db=db,
    )

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    include_routers(dp)
    register_middlewares(dp, config=config, db=db, apscheduler=apscheduler)

    app = web.Application()
    app.router.add_get("/health", health_handler)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.bot.WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 8080))
    logger.info("listening on 0.0.0.0:%d", port)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
