from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


ALL_TICKETS_BUTTON = "📋 Все билеты"
HELP_BUTTON = "❓ Помощь"
ADMIN_BUTTON = "⚙️ Админка"
UPLOAD_BUTTON = "➕ Добавить билет"
CANCEL_BUTTON = "❌ Отмена"


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    keyboard = [[
        KeyboardButton(text=ALL_TICKETS_BUTTON),
        KeyboardButton(text=HELP_BUTTON),
    ]]
    if is_admin:
        keyboard.append([
            KeyboardButton(text=ADMIN_BUTTON),
            KeyboardButton(text=UPLOAD_BUTTON),
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
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
            [InlineKeyboardButton(text="🧹 Удалить ВСЕ билеты", callback_data="admin_delete_all")],
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


def add_more_images_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить ещё график", callback_data="img_more"),
                InlineKeyboardButton(text="✅ Готово", callback_data="img_done"),
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


def confirm_delete_all_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧹 Да, удалить ВСЕ", callback_data="del_all_confirm"),
                InlineKeyboardButton(text="🔙 Отмена", callback_data="del_all_cancel"),
            ]
        ]
    )


def image_actions_inline(can_add: bool = True) -> InlineKeyboardMarkup:
    inline_keyboard = []
    if can_add:
        inline_keyboard.append(
            [InlineKeyboardButton(text="➕ Добавить график", callback_data="imgact_add")]
        )

    inline_keyboard.extend(
        [
            [
                InlineKeyboardButton(text="🔄 Заменить", callback_data="imgact_replace"),
                InlineKeyboardButton(text="🗑 Удалить графики", callback_data="imgact_delete"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="imgact_back")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def edit_actions_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Заменить текст", callback_data="edit_replace_text")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_back")],
        ]
    )
