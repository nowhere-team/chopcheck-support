import os

from aiogram.client.session.aiohttp import AiohttpSession


def make_bot_session() -> AiohttpSession | None:
    """Build a Bot session routed through ``TELEGRAM_PROXY_URL`` when set.

    aiohttp (and therefore aiogram) ignores the ``HTTP(S)_PROXY`` environment
    variables, so the proxy must be passed explicitly. This lets the bot reach
    api.telegram.org from hosts where telegram is network-blocked (e.g. RU prod),
    while leaving all other I/O (sqlite, redis, remnawave) direct.

    Returns ``None`` when no proxy is configured, so ``Bot`` falls back to its
    default session.
    """
    proxy = os.environ.get("TELEGRAM_PROXY_URL", "").strip()
    if not proxy:
        return None
    return AiohttpSession(proxy=proxy)
