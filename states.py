from aiogram.fsm.state import State, StatesGroup


class UploadTicket(StatesGroup):
    waiting_for_number = State()
    waiting_for_text = State()
    waiting_for_image_choice = State()
    waiting_for_image = State()
    waiting_for_more_images = State()


class EditTicket(StatesGroup):
    waiting_for_number = State()
    waiting_for_action = State()
    waiting_for_new_text = State()
    waiting_for_image = State()
    waiting_for_more_images = State()


class ManageImage(StatesGroup):
    waiting_for_number = State()
    waiting_for_action = State()
    waiting_for_image = State()


class DeleteTicket(StatesGroup):
    waiting_for_number = State()
    waiting_for_confirmation = State()
