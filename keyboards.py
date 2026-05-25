from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


ALL_TICKETS_BUTTON = "📋 Все билеты"
HELP_BUTTON = "❓ Помощь"
ADMIN_BUTTON = "⚙️ Админка"
CANCEL_BUTTON = "❌ Отмена"


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [
        KeyboardButton(text=ALL_TICKETS_BUTTON),
        KeyboardButton(text=HELP_BUTTON),
    ]
    if is_admin:
        buttons.append(KeyboardButton(text=ADMIN_BUTTON))

    return ReplyKeyboardMarkup(
        keyboard=[buttons],
        resize_keyboard=True,
        input_field_placeholder="Отправь номера билетов",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_BUTTON)]],
        resize_keyboard=True,
    )


def admin_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Загрузить билет", callback_data="admin_upload")],
            [InlineKeyboardButton(text="✏️ Редактировать билет", callback_data="admin_edit")],
            [InlineKeyboardButton(text="📊 Добавить/заменить график", callback_data="admin_image")],
            [InlineKeyboardButton(text="🗑 Удалить билет", callback_data="admin_delete")],
            [InlineKeyboardButton(text="📋 Статус загрузки", callback_data="admin_status")],
        ]
    )


def image_choice_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Да", callback_data="img_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="img_no"),
            ]
        ]
    )


def confirm_overwrite_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, перезаписать", callback_data="overwrite_yes"),
                InlineKeyboardButton(text="Отмена", callback_data="overwrite_cancel"),
            ]
        ]
    )


def confirm_delete_inline(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"del_confirm_{ticket_id}"),
                InlineKeyboardButton(text="🔙 Отмена", callback_data="del_cancel"),
            ]
        ]
    )


def image_actions_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Заменить", callback_data="imgact_replace"),
                InlineKeyboardButton(text="🗑 Удалить график", callback_data="imgact_delete"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="imgact_back")],
        ]
    )


def edit_actions_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Заменить текст", callback_data="edit_replace_text")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_back")],
        ]
    )
