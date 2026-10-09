import os
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════
#   Bot
# ═══════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8880513739:AAFMxifxUwJ2_AShEXo5bslTaKvukjcVCF8").strip()
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN مفقود!")

# ═══════════════════════════════════════════════════════════
#   Admins
# ═══════════════════════════════════════════════════════════
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "6861802815")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]
if not ADMIN_IDS:
    raise ValueError("❌ ADMIN_IDS مفقود!")

# ═══════════════════════════════════════════════════════════
#   Support
# ═══════════════════════════════════════════════════════════
SUPPORT_CHANNEL = os.getenv("SUPPORT_CHANNEL", "https://t.me/asrom_xit")

# ═══════════════════════════════════════════════════════════
#   Database
# ═══════════════════════════════════════════════════════════
DATA_FILE = "data.json"