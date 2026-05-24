# Telegram-бот «Коллоквиум»

Хранение билетов в SQLite, загрузка билетов администратором через Telegram, парсинг raw-текста с LaTeX в HTML и выдача выбранных билетов файлом.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

Заполните `.env`:

```env
BOT_TOKEN=telegram_bot_token
ADMIN_ID=123456789
```

## Запуск

```bash
python bot.py
```

## Использование

Админские команды:

```text
/upload
/status
/delete 22
/cancel
```

Пользовательский запрос билетов:

```text
дай 22 билет
```
