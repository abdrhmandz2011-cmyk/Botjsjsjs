"""
💾 قاعدة بيانات محلية — لا Firebase
كل شيء في data.json
"""

import json
import os
import random
import string
import shutil
from datetime import datetime
from threading import Lock

from config import DATA_FILE

LOCK = Lock()

DEFAULT_DATA = {
    "settings": {
        "bot_name": "ASROM SHOP",
        "welcome": "👋 أهلاً بك في ASROM SHOP",
        "support_channel": "https://t.me/asrom_xit",
        "proofs_channel": "",
        "required_channels": [],
        "daily_gift_points": 10,
        "daily_gift_cooldown": 86400,
        "referral_points": 20,
        "currency_emoji": "💰"
    },
    "users": {},
    "products": {},
    "orders": {},
    "points_links": {},
    "maintenance": {"active": False, "message": "🔧 المتجر تحت الصيانة", "end_time": 0},
    "stats": {"total_sales": 0, "total_points_given": 0}
}


def load() -> dict:
    if not os.path.exists(DATA_FILE):
        save(dict(DEFAULT_DATA))
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with LOCK:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        for k, v in DEFAULT_DATA.items():
            if k not in data:
                data[k] = v
        for sk, sv in DEFAULT_DATA["settings"].items():
            if sk not in data.get("settings", {}):
                data.setdefault("settings", {})[sk] = sv
        return data
    except Exception as e:
        print(f"❌ Load error: {e}")
        return json.loads(json.dumps(DEFAULT_DATA))


def save(data: dict) -> bool:
    try:
        with LOCK:
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        return True
    except Exception as e:
        print(f"❌ Save: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#   Settings
# ═══════════════════════════════════════════════════════════
def get_settings() -> dict:
    return load().get("settings", {})


def update_settings(updates: dict) -> bool:
    data = load()
    data["settings"].update(updates)
    return save(data)


def get_proofs_channel() -> str:
    return get_settings().get("proofs_channel", "").strip()


def get_required_channels() -> list:
    ch = get_settings().get("required_channels", [])
    return ch if isinstance(ch, list) else []


def add_required_channel(chat_id: str, title: str = "", url: str = "") -> bool:
    data = load()
    ch = data["settings"].get("required_channels", [])
    if not isinstance(ch, list):
        ch = []
    for c in ch:
        if c.get("chat_id") == chat_id:
            return False
    ch.append({"chat_id": chat_id, "title": title or chat_id, "url": url})
    data["settings"]["required_channels"] = ch
    return save(data)


def remove_required_channel(chat_id: str) -> bool:
    data = load()
    ch = data["settings"].get("required_channels", [])
    if not isinstance(ch, list):
        return False
    new = [c for c in ch if c.get("chat_id") != chat_id]
    if len(new) == len(ch):
        return False
    data["settings"]["required_channels"] = new
    return save(data)


# ═══════════════════════════════════════════════════════════
#   Users
# ═══════════════════════════════════════════════════════════
def get_user(user_id: int) -> dict:
    return load().get("users", {}).get(str(user_id), {})


def get_all_users() -> dict:
    return load().get("users", {})


def register_user(user_id: int, first_name: str, username: str = "", referred_by=None):
    data = load()
    uid = str(user_id)
    if uid in data["users"]:
        return data["users"][uid], False

    code = "REF_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while any(u.get("referral_code") == code for u in data["users"].values()):
        code = "REF_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    user = {
        "user_id": user_id,
        "first_name": first_name,
        "username": username,
        "points": 0,
        "referral_code": code,
        "referred_by": referred_by,
        "total_referrals": 0,
        "joined_at": int(datetime.now().timestamp()),
        "last_gift": 0,
        "purchases": [],
        "total_spent": 0,
        "is_banned": False
    }

    data["users"][uid] = user
    save(data)
    return user, True


def save_user(user_id: int, updates: dict) -> bool:
    data = load()
    uid = str(user_id)
    if uid not in data["users"]:
        return False
    data["users"][uid].update(updates)
    return save(data)


def add_points(user_id: int, amount: int) -> bool:
    data = load()
    uid = str(user_id)
    if uid not in data["users"]:
        return False
    data["users"][uid]["points"] = data["users"][uid].get("points", 0) + amount
    if amount > 0:
        data["stats"]["total_points_given"] = data["stats"].get("total_points_given", 0) + amount
    return save(data)


def remove_points(user_id: int, amount: int) -> bool:
    return add_points(user_id, -amount)


def get_total_users() -> int:
    return len(load().get("users", {}))


def ban_user(user_id: int, banned: bool = True) -> bool:
    return save_user(user_id, {"is_banned": banned})


def find_user_by_code(code: str) -> dict:
    for u in get_all_users().values():
        if u.get("referral_code") == code:
            return u
    return {}


# ═══════════════════════════════════════════════════════════
#   Products
# ═══════════════════════════════════════════════════════════
def get_products(active_only: bool = True) -> dict:
    products = load().get("products", {})
    if not active_only:
        return products
    return {k: v for k, v in products.items() if v.get("active", True)}


def get_product(pid: str) -> dict:
    return load().get("products", {}).get(pid, {})


def add_product(pid: str, product: dict) -> bool:
    data = load()
    product["created_at"] = int(datetime.now().timestamp())
    product["sold_count"] = 0
    data["products"][pid] = product
    return save(data)


def update_product(pid: str, updates: dict) -> bool:
    data = load()
    if pid not in data["products"]:
        return False
    data["products"][pid].update(updates)
    return save(data)


def delete_product(pid: str) -> bool:
    data = load()
    if pid in data["products"]:
        del data["products"][pid]
        return save(data)
    return False


def add_content_to_product(pid: str, content_item: dict) -> bool:
    data = load()
    if pid not in data["products"]:
        return False
    if "contents" not in data["products"][pid]:
        data["products"][pid]["contents"] = []
    data["products"][pid]["contents"].append(content_item)
    return save(data)


def remove_content_from_product(pid: str, index: int) -> bool:
    data = load()
    if pid not in data["products"]:
        return False
    contents = data["products"][pid].get("contents", [])
    if 0 <= index < len(contents):
        del contents[index]
        data["products"][pid]["contents"] = contents
        return save(data)
    return False


def get_available_content(pid: str):
    product = get_product(pid)
    if not product:
        return None
    mode = product.get("delivery_mode", "single")
    if mode == "single":
        content = product.get("content", {})
        if not content or not content.get("data"):
            return None
        return content
    elif mode == "multi":
        contents = product.get("contents", [])
        sold = product.get("sold_count", 0)
        if sold >= len(contents):
            return None
        return contents[sold]
    return None


def increment_sold(pid: str) -> bool:
    data = load()
    if pid not in data["products"]:
        return False
    data["products"][pid]["sold_count"] = data["products"][pid].get("sold_count", 0) + 1
    return save(data)


def is_product_available(pid: str) -> bool:
    product = get_product(pid)
    if not product:
        return False
    mode = product.get("delivery_mode", "single")
    if mode == "single":
        return True
    if mode == "multi":
        contents = product.get("contents", [])
        sold = product.get("sold_count", 0)
        return sold < len(contents)
    return False


def get_product_stock(pid: str) -> int:
    product = get_product(pid)
    if not product:
        return 0
    mode = product.get("delivery_mode", "single")
    if mode == "single":
        return -1
    contents = product.get("contents", [])
    sold = product.get("sold_count", 0)
    return max(0, len(contents) - sold)


# ═══════════════════════════════════════════════════════════
#   Orders
# ═══════════════════════════════════════════════════════════
def add_order(order_id: str, order: dict) -> bool:
    data = load()
    data["orders"][order_id] = order
    data["stats"]["total_sales"] = data["stats"].get("total_sales", 0) + 1
    return save(data)


def get_user_orders(user_id: int) -> list:
    orders = load().get("orders", {})
    return [o for o in orders.values() if o.get("user_id") == user_id]


# ═══════════════════════════════════════════════════════════
#   Maintenance
# ═══════════════════════════════════════════════════════════
def get_maintenance() -> dict:
    return load().get("maintenance", {})


def set_maintenance(active=None, message=None, end_time=None) -> bool:
    data = load()
    if active is not None:
        data["maintenance"]["active"] = active
    if message is not None:
        data["maintenance"]["message"] = message
    if end_time is not None:
        data["maintenance"]["end_time"] = end_time
    return save(data)


def is_maintenance_active() -> bool:
    m = get_maintenance()
    if not m.get("active", False):
        return False
    end = m.get("end_time", 0)
    if end > 0:
        now = int(datetime.now().timestamp())
        if now > end:
            set_maintenance(active=False, end_time=0)
            return False
    return True


# ═══════════════════════════════════════════════════════════
#   Stats
# ═══════════════════════════════════════════════════════════
def get_stats() -> dict:
    data = load()
    s = data.get("stats", {})
    s["total_users"] = len(data.get("users", {}))
    s["total_products"] = len(data.get("products", {}))
    return s


def get_top_users(limit: int = 10) -> list:
    return sorted(get_all_users().values(), key=lambda u: u.get("points", 0), reverse=True)[:limit]


def get_top_referrers(limit: int = 10) -> list:
    return sorted(get_all_users().values(), key=lambda u: u.get("total_referrals", 0), reverse=True)[:limit]


# ═══════════════════════════════════════════════════════════
#   Points Links
# ═══════════════════════════════════════════════════════════
def get_points_links() -> dict:
    links = load().get("points_links", {})
    return links if isinstance(links, dict) else {}


def get_points_link(code: str) -> dict:
    return get_points_links().get(code, {})


def add_points_link(code: str, data_: dict) -> bool:
    all_data = load()
    if "points_links" not in all_data:
        all_data["points_links"] = {}
    data_["code"] = code
    data_["created_at"] = int(datetime.now().timestamp())
    data_["uses"] = 0
    data_["claimed_by"] = {}
    data_["active"] = True
    all_data["points_links"][code] = data_
    return save(all_data)


def delete_points_link(code: str) -> bool:
    all_data = load()
    if "points_links" not in all_data:
        return False
    if code in all_data["points_links"]:
        del all_data["points_links"][code]
        return save(all_data)
    return False


def is_points_link_valid(link: dict) -> tuple:
    if not link or not isinstance(link, dict):
        return False, "غير موجود"
    if not link.get("active", True):
        return False, "معطل"
    expire_at = link.get("expire_at", 0) or 0
    if expire_at > 0 and int(datetime.now().timestamp()) > expire_at:
        return False, "منتهي"
    max_uses = link.get("max_uses", 0) or 0
    uses = link.get("uses", 0) or 0
    if max_uses > 0 and uses >= max_uses:
        return False, "استُنفد"
    return True, ""


def claim_points_link(code: str, user_id: int) -> tuple:
    data = load()
    if "points_links" not in data or code not in data["points_links"]:
        return False, 0, "❌ الرابط غير موجود"
    link = data["points_links"][code]
    valid, reason = is_points_link_valid(link)
    if not valid:
        return False, 0, f"❌ الرابط {reason}"
    claimed = link.get("claimed_by", {}) or {}
    if str(user_id) in claimed:
        return False, 0, "⚠️ استخدمت هذا الرابط من قبل"
    amount = link.get("amount", 0)
    if amount <= 0:
        return False, 0, "❌ قيمة النقاط غير صحيحة"
    uid = str(user_id)
    if uid not in data["users"]:
        return False, 0, "❌ سجل أولاً بـ /start"
    data["users"][uid]["points"] = data["users"][uid].get("points", 0) + amount
    data["stats"]["total_points_given"] = data["stats"].get("total_points_given", 0) + amount
    link["uses"] = link.get("uses", 0) + 1
    if "claimed_by" not in link or not isinstance(link["claimed_by"], dict):
        link["claimed_by"] = {}
    link["claimed_by"][str(user_id)] = int(datetime.now().timestamp())
    data["points_links"][code] = link
    save(data)
    return True, amount, "✅ تم استلام النقاط"


# ═══════════════════════════════════════════════════════════
#   Backup
# ═══════════════════════════════════════════════════════════
def backup() -> str:
    if not os.path.exists(DATA_FILE):
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"data_backup_{ts}.json"
    try:
        shutil.copy2(DATA_FILE, name)
        return name
    except Exception:
        return ""