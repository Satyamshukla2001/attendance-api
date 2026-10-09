import os
from zoneinfo import ZoneInfo

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("DB_NAME", "attendance")
TZ_NAME = "Asia/Kolkata"
IST = ZoneInfo(TZ_NAME)

MAX_SHIFT_HOURS = 16          # a single punch pair can't exceed this
MIN_SHIFT_MINUTES = 1         # punch-out must be at least this after punch-in
MAX_CORRECTION_DAYS = 31      # corrections only allowed for recent records
