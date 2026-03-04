from __future__ import annotations

import html
from typing import Iterable

from aiogram import F, Router
from aiogram.filters import Command, MagicData, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from app.bot.manager import Manager
from app.bot.utils.redis import QuickReplyStorage, QuickReplyAttachment, QuickReplyItem
from app.bot.types.album import Album


router = Router(name="quick_replies")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class QuickReplyStates(StatesGroup):
    waiting_title = State()
    waiting_content = State()
    editing_title = State()
    editing_content = State()


def _collect_attachments(
    message: Message,
    *,
    album: Album | None = None,
) -> tuple[str | None, list[QuickReplyAttachment]]:
    text = message.text or None
    attachments: list[QuickReplyAttachment] = []

    if album is not None:
        caption = album.caption
        first = True
        for media_type in album.media_types:
            for media in getattr(album, media_type) or []:
                attachments.append(
                    QuickReplyAttachment(
                        type=media_type,
                        file_id=media.file_id,
                        caption=caption if first else None,
                    )
                )
                first = False
        return caption or text, attachments

    if message.photo:
        file_id = message.photo[-1].file_id
        attachments.append(
            QuickReplyAttachment(
                type="photo", file_id=file_id, caption=message.caption or None
            )
        )
        if message.caption:
            text = None
    elif message.video:
        attachments.append(
            QuickReplyAttachment(
                type="video",
                file_id=message.video.file_id,
                caption=message.caption or None,
            )
        )
        if message.caption:
            text = None
    elif message.document:
        attachments.append(
            QuickReplyAttachment(
                type="document",
                file_id=message.document.file_id,
                caption=message.caption or None,
            )
        )
        if message.caption:
            text = None
    elif message.animation:
        attachments.append(
            QuickReplyAttachment(
                type="animation",
                file_id=message.animation.file_id,
                caption=message.caption or None,
            )
        )
        if message.caption:
            text = None
    elif message.audio:
        attachments.append(
            QuickReplyAttachment(
                type="audio",
                file_id=message.audio.file_id,
                caption=message.caption or None,
            )
        )
        if message.caption:
            text = None
    elif message.voice:
        attachments.append(
            QuickReplyAttachment(
                type="voice", file_id=message.voice.file_id, caption=None
            )
        )
    elif message.video_note:
        attachments.append(
            QuickReplyAttachment(
                type="video_note", file_id=message.video_note.file_id, caption=None
            )
        )

    return text, attachments


def _render_admin_overview(
    items: Iterable[QuickReplyItem],
) -> tuple[str, InlineKeyboardBuilder]:
    items = list(items)
    builder = InlineKeyboardBuilder()
    lines = ["<b>Быстрые ответы</b>"]
    if not items:
        lines.append("Список пуст. Добавьте первый ответ.")
    else:
        lines.append("Выберите элемент для редактирования или добавьте новый ответ.")
        for idx, item in enumerate(items, start=1):
            builder.button(
                text=f"{idx}. {item.title}", callback_data=f"qr:manage:{item.id}"
            )
            lines.append(f"{idx}. {hbold(html.escape(item.title))}")
    builder.button(text="➕ Добавить ответ", callback_data="qr:add")
    builder.button(text="⬅️ Назад", callback_data="admin:menu")
    builder.adjust(1)
    return "\n".join(lines), builder


async def _show_admin_overview(manager: Manager, storage: QuickReplyStorage) -> None:
    items = await storage.list_items()
    text, builder = _render_admin_overview(items)
    await manager.state.set_state(None)
    await manager.send_message(
        text, reply_markup=builder.as_markup(), replace_previous=False
    )


async def _show_admin_item_menu(manager: Manager, item: QuickReplyItem) -> None:
    await manager.state.update_data(qr_item_id=item.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Переименовать", callback_data=f"qr:rename:{item.id}")
    builder.button(text="📝 Обновить ответ", callback_data=f"qr:content:{item.id}")
    builder.button(text="🗑 Удалить", callback_data=f"qr:delete:{item.id}")
    builder.button(text="⬅️ Назад", callback_data="qr:admin_back")
    builder.adjust(1)

    preview_lines = [
        f"<b>{html.escape(item.title)}</b>",
        "",
    ]
    if item.text:
        preview_lines.append(html.escape(item.text))
    else:
        preview_lines.append("<i>Текст отсутствует</i>")
    if item.attachments:
        preview_lines.append("")
        preview_lines.append(f"Вложения: {len(item.attachments)}")

    await manager.send_message(
        "\n".join(preview_lines),
        reply_markup=builder.as_markup(),
        replace_previous=False,
    )


@router.message(
    Command("quick"), MagicData(F.event_from_user.id == F.config.bot.DEV_ID)
)  # type: ignore[attr-defined]
async def admin_command_quick(
    message: Message, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    await _show_admin_overview(manager, quick_replies)
    await manager.delete_message(message)


@router.callback_query(
    F.data == "admin:quick_replies",
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_open_quick_replies(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    await _show_admin_overview(manager, quick_replies)
    await call.answer()


@router.callback_query(
    F.data == "qr:add",
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_add_quick_reply(call: CallbackQuery, manager: Manager) -> None:
    await manager.state.set_state(QuickReplyStates.waiting_title)
    await manager.state.update_data(qr_item_id=None)
    await manager.send_message(
        "Введите заголовок для быстрого ответа.", replace_previous=False
    )
    await call.answer()


@router.message(StateFilter(QuickReplyStates.waiting_title))
async def admin_receive_title(message: Message, manager: Manager) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Попробуйте ещё раз.")
        return

    await manager.state.update_data(qr_title=title)
    await manager.state.set_state(QuickReplyStates.waiting_content)
    await manager.send_message(
        "Отправьте ответ одним сообщением. Можно приложить фото, видео или документ с подписью.",
        replace_previous=False,
    )
    await manager.delete_message(message)


@router.message(StateFilter(QuickReplyStates.waiting_content))
async def admin_receive_content(
    message: Message,
    manager: Manager,
    quick_replies: QuickReplyStorage,
    album: Album | None = None,
) -> None:
    try:
        text, attachments = _collect_attachments(message, album=album)
    except ValueError:
        await message.answer(
            "Медиа-альбомы пока не поддерживаются. Отправьте ответ одним сообщением."
        )
        return

    if text is None and not attachments:
        await message.answer(
            "Ответ должен содержать текст или вложение. Попробуйте ещё раз."
        )
        return

    state = await manager.state.get_data()
    title = state.get("qr_title")
    if not title:
        await manager.state.set_state(None)
        await message.answer(
            "Не удалось определить заголовок. Начните добавление заново."
        )
        return

    await quick_replies.add_item(title=title, text=text, attachments=attachments)
    await manager.state.set_state(None)
    await manager.state.update_data(qr_title=None)
    await manager.delete_message(message)
    await _show_admin_overview(manager, quick_replies)


@router.callback_query(
    F.data.startswith("qr:manage:"),
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_manage_item(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    item_id = call.data.split(":", maxsplit=2)[-1]
    item = await quick_replies.get_item(item_id)
    if item is None:
        await call.answer("Элемент не найден.", show_alert=True)
        return

    await manager.state.update_data(qr_item_id=item_id)
    await _show_admin_item_menu(manager, item)
    await call.answer()


@router.callback_query(
    F.data.startswith("qr:rename:"),
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_start_rename(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    item_id = call.data.split(":", maxsplit=2)[-1]
    item = await quick_replies.get_item(item_id)
    if item is None:
        await call.answer("Элемент не найден.", show_alert=True)
        return

    await manager.state.set_state(QuickReplyStates.editing_title)
    await manager.state.update_data(qr_item_id=item_id)
    await manager.send_message(
        f"Текущий заголовок: <b>{html.escape(item.title)}</b>\nВведите новый заголовок.",
        replace_previous=False,
    )
    await call.answer()


@router.message(StateFilter(QuickReplyStates.editing_title))
async def admin_rename_item(
    message: Message, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    new_title = (message.text or "").strip()
    if not new_title:
        await message.answer("Заголовок не может быть пустым. Попробуйте снова.")
        return

    state = await manager.state.get_data()
    item_id = state.get("qr_item_id")
    if not item_id:
        await manager.state.set_state(None)
        await message.answer("Не удалось определить элемент. Начните заново.")
        return

    updated = await quick_replies.rename_item(item_id, new_title)
    if updated is None:
        await manager.state.set_state(None)
        await message.answer("Элемент уже удалён.")
        return

    await manager.state.set_state(None)
    await manager.delete_message(message)
    await _show_admin_item_menu(manager, updated)


@router.callback_query(
    F.data.startswith("qr:content:"),
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_start_update_content(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    item_id = call.data.split(":", maxsplit=2)[-1]
    item = await quick_replies.get_item(item_id)
    if item is None:
        await call.answer("Элемент не найден.", show_alert=True)
        return

    await manager.state.set_state(QuickReplyStates.editing_content)
    await manager.state.update_data(qr_item_id=item_id)
    await manager.send_message(
        "Отправьте новое содержимое ответа одним сообщением. Можно приложить медиафайл.",
        replace_previous=False,
    )
    await call.answer()


@router.message(StateFilter(QuickReplyStates.editing_content))
async def admin_update_content(
    message: Message,
    manager: Manager,
    quick_replies: QuickReplyStorage,
    album: Album | None = None,
) -> None:
    try:
        text, attachments = _collect_attachments(message, album=album)
    except ValueError:
        await message.answer(
            "Медиа-альбомы пока не поддерживаются. Отправьте ответ одним сообщением."
        )
        return

    if text is None and not attachments:
        await message.answer(
            "Ответ должен содержать текст или вложение. Попробуйте ещё раз."
        )
        return

    state = await manager.state.get_data()
    item_id = state.get("qr_item_id")
    if not item_id:
        await manager.state.set_state(None)
        await message.answer("Не удалось определить элемент. Начните заново.")
        return

    updated = await quick_replies.update_content(
        item_id, text=text, attachments=attachments
    )
    if updated is None:
        await manager.state.set_state(None)
        await message.answer("Элемент уже удалён.")
        return

    await manager.state.set_state(None)
    await manager.delete_message(message)
    await _show_admin_item_menu(manager, updated)


@router.callback_query(
    F.data == "qr:admin_back",
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_back_to_list(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    await _show_admin_overview(manager, quick_replies)
    await call.answer()


@router.callback_query(
    F.data.startswith("qr:delete:"),
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
async def admin_delete_item(
    call: CallbackQuery, manager: Manager, quick_replies: QuickReplyStorage
) -> None:
    item_id = call.data.split(":", maxsplit=2)[-1]
    await quick_replies.delete_item(item_id)
    await manager.state.set_state(None)
    await _show_admin_overview(manager, quick_replies)
    await call.answer("Удалено")
