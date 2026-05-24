import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)

DB_PATH = str(BASE_DIR / "colloquium.db")
IMAGES_DIR = str(BASE_DIR / "images")
TMP_DIR = str(BASE_DIR / "tmp")
TOTAL_TICKETS = 33
