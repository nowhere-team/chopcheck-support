from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from app.bot.manager import Manager


class ManagerMiddleware(BaseMiddleware):
    """
    Middleware for passing manager object.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state: FSMContext = data.get("state")
        state_data = await state.get_data()
        config = data["config"].bot

        if not config.LANGUAGE_PROMPT_ENABLED:
            language_code = config.DEFAULT_LANGUAGE
        else:
            language_code = state_data.get("language_code")

            if language_code is None:
                user_data = data.get("user_data")
                if user_data and user_data.language_code:
                    language_code = user_data.language_code

            if language_code is None:
                language_code = config.DEFAULT_LANGUAGE

        # Create a Manager instance with a custom emoji, data, and language_code
        manager = Manager("💎", data, language_code)
        # Pass the manager object to the handler function
        data["manager"] = manager

        # Call the handler function with the event and data
        return await handler(event, data)
