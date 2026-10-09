<"""
🛒 ASROM SHOP — Bot
- Force Sub
- Points + Referral + Daily Gift
- Shop + Points Links
- Maintenance
- Admin Panel
"""

import logging
import asyncio
import random
import string
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters,
)

from config import BOT_TOKEN, ADMIN_IDS
import database as db

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ShopBot")


# ═══════════════════════════════════════════════════════════
#   States
# ═══════════════════════════════════════════════════════════
(
    P_NAME, P_EMOJI, P_DESC, P_PRICE, P_MODE, P_FIRST_CONTENT,
    AC_CONTENT, PE_VALUE,
    UP_USER, UP_AMOUNT, UB_USER,
    MSG_USER, MSG_TEXT, BC_TEXT,
    MAINT_TIME, MAINT_MSG, SET_VALUE,
    ADD_CH_ID, ADD_CH_TITLE,
    PL_AMOUNT, PL_MAX_USES, PL_EXPIRE_HOURS,
) = range(22)


# ═══════════════════════════════════════════════════════════
#   Helpers
# ═══════════════════════════════════════════════════════════
def is_admin(uid): return uid in ADMIN_IDS

def esc(t):
    if not t: return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def s(): return db.get_settings()
def cur(): return s().get("currency_emoji", "💰")

def fmt(n):
    try: return f"{int(n):,}"
    except: return str(n)

def fmt_rem(sec):
    if sec <= 0: return "الآن"
    h, m, ss = sec // 3600, (sec % 3600) // 60, sec % 60
    if h > 0: return f"{h}س {m}د"
    if m > 0: return f"{m}د {ss}ث"
    return f"{ss}ث"

def stock_label(pid):
    st = db.get_product_stock(pid)
    if st == -1: return "♾️ لا نهائي"
    if st == 0: return "❌ نفدت"
    return f"📦 متوفر: {st}"


# ═══════════════════════════════════════════════════════════
#   Cancel helpers
# ═══════════════════════════════════════════════════════════
def cancel_only_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_conv")
    ]])


def cancel_kb(rows=None):
    rows = list(rows) if rows else []
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_conv")])
    return InlineKeyboardMarkup(rows)


async def cb_cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("❌ تم الإلغاء")
    context.user_data.clear()
    try:
        await q.edit_message_text(
            "❌ <b>تم الإلغاء</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")
            ]]),
        )
    except Exception:
        pass
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Force Subscription
# ═══════════════════════════════════════════════════════════
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    channels = db.get_required_channels()
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch.get("chat_id"), user_id)
            if member.status in [ChatMember.LEFT, ChatMember.BANNED]:
                missing.append(ch)
        except Exception as e:
            logger.warning(f"Sub check {ch.get('chat_id')}: {e}")
            missing.append(ch)
    return len(missing) == 0, missing


def subscription_kb(missing_channels):
    rows = []
    for ch in missing_channels:
        url = ch.get("url", "") or f"https://t.me/{str(ch.get('chat_id','')).lstrip('@')}"
        rows.append([InlineKeyboardButton(f"📢 {ch.get('title','قناة')}", url=url)])
    rows.append([InlineKeyboardButton("✅ تحقّق من الاشتراك", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)


async def require_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if is_admin(user.id):
        return True
    is_sub, missing = await check_subscription(user.id, context)
    if is_sub:
        return True
    text = (
        "⛔ <b>الاشتراك الإجباري</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ يجب الاشتراك في القنوات التالية لاستخدام البوت:"
    )
    kb = subscription_kb(missing)
    if update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
            except Exception:
                pass
    return False


# ═══════════════════════════════════════════════════════════
#   Keyboards
# ═══════════════════════════════════════════════════════════
def main_menu_kb(uid):
    rows = [
        [InlineKeyboardButton("🛍️ المتجر", callback_data="shop")],
        [InlineKeyboardButton("🎁 الهدية اليومية", callback_data="daily"),
         InlineKeyboardButton("💰 رصيدي", callback_data="balance")],
        [InlineKeyboardButton("👥 دعوة أصدقاء", callback_data="referral"),
         InlineKeyboardButton("🎒 مشترياتي", callback_data="purchases")],
        [InlineKeyboardButton("📞 الدعم", url=s().get("support_channel", "https://t.me"))],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def shop_kb():
    products = db.get_products(active_only=True)
    keyboard, row = [], []
    for pid, p in products.items():
        emoji, name, price = p.get("emoji", "📦"), p.get("name", "?"), p.get("price", 0)
        avail = db.is_product_available(pid)
        status = "" if avail else " ❌"
        btn = InlineKeyboardButton(
            f"{emoji} {name} — {fmt(price)}{status}",
            callback_data=f"view_{pid}"
        )
        if len(row) == 1:
            keyboard.append(row); row = []
        row.append(btn)
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)


def product_kb(pid):
    if db.is_product_available(pid):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 شراء", callback_data=f"buy_{pid}")],
            [InlineKeyboardButton("⬅️ رجوع للمتجر", callback_data="shop")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ نفدت الكمية", callback_data="noop")],
        [InlineKeyboardButton("⬅️ رجوع للمتجر", callback_data="shop")],
    ])


def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm_stats")],
        [InlineKeyboardButton("📦 المنتجات", callback_data="adm_products"),
         InlineKeyboardButton("➕ إضافة منتج", callback_data="adm_add_p")],
        [InlineKeyboardButton("👥 المستخدمون", callback_data="adm_users"),
         InlineKeyboardButton("💰 إعطاء نقاط", callback_data="adm_give")],
        [InlineKeyboardButton("🎁 روابط النقاط", callback_data="adm_pl")],
        [InlineKeyboardButton("🔨 حظر", callback_data="adm_ban"),
         InlineKeyboardButton("💬 رسالة", callback_data="adm_msg")],
        [InlineKeyboardButton("📢 بث", callback_data="adm_bc")],
        [InlineKeyboardButton("📣 قنوات الاشتراك", callback_data="adm_channels")],
        [InlineKeyboardButton("🔧 الصيانة", callback_data="adm_maint"),
         InlineKeyboardButton("🎨 الإعدادات", callback_data="adm_set")],
        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="adm_backup"),
         InlineKeyboardButton("🏠 القائمة", callback_data="back_main")],
    ])


# ═══════════════════════════════════════════════════════════
#   Notifications
# ═══════════════════════════════════════════════════════════
async def notify_admins_purchase(context, user, product, price, new_balance):
    text = (
        f"🛒 <b>عملية شراء جديدة!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>المشتري:</b> {esc(user.first_name)}\n"
        f"🔗 <b>المعرف:</b> @{user.username or '—'}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📦 <b>المنتج:</b> {product.get('emoji','')} {esc(product.get('name',''))}\n"
        f"💸 <b>السعر:</b> {fmt(price)} نقطة\n"
        f"{cur()} <b>رصيده:</b> {fmt(new_balance)}\n\n"
        f"📅 <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Notify admin {admin_id}: {e}")


async def post_proof(context, user, product, price, remaining_stock):
    proofs_channel = db.get_proofs_channel()
    if not proofs_channel:
        return
    username_str = f"@{user.username}" if user.username else "—"
    user_id_str = str(user.id)
    hidden_id = (user_id_str[:4] + "***" + user_id_str[-2:]) if len(user_id_str) > 4 else user_id_str
    if remaining_stock == -1:
        stock_line = "♾️ <b>المخزون:</b> لا نهائي"
    elif remaining_stock == 0:
        stock_line = "🔥 <b>المخزون:</b> آخر قطعة!"
    else:
        stock_line = f"📦 <b>المتبقي:</b> {remaining_stock}"
    text = (
        f"✅ <b>دليل تسليم جديد</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛒 <b>المنتج:</b> {product.get('emoji','')} {esc(product.get('name',''))}\n"
        f"💰 <b>السعر:</b> {fmt(price)} نقطة\n\n"
        f"👤 <b>المشتري:</b> {esc(user.first_name)}\n"
        f"🔗 <b>المعرف:</b> {username_str}\n"
        f"🆔 <b>ID:</b> <code>{hidden_id}</code>\n\n"
        f"{stock_line}\n"
        f"📅 <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"🤖 <i>تم التسليم تلقائياً بواسطة البوت</i>"
    )
    try:
        await context.bot.send_message(chat_id=proofs_channel, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Post proof failed [{proofs_channel}]: {e}")


# ═══════════════════════════════════════════════════════════
#   /start
# ═══════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if db.is_maintenance_active() and not is_admin(user.id):
        m = db.get_maintenance()
        msg = m.get("message", "🔧 المتجر تحت الصيانة")
        end = m.get("end_time", 0)
        if end > 0:
            msg += f"\n\n⏰ {datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M')}"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    if not await require_subscription(update, context):
        return

    ref = None
    if context.args and context.args[0].startswith("REF_"):
        r = db.find_user_by_code(context.args[0])
        if r and r.get("user_id") != user.id:
            ref = r.get("user_id")

    ud, is_new = db.register_user(user.id, user.first_name or "", user.username or "", ref)

    # Points Link
    if context.args and context.args[0].startswith("PTS_"):
        code = context.args[0]
        success, amount, msg = db.claim_points_link(code, user.id)
        if success:
            new_ud = db.get_user(user.id)
            await update.message.reply_text(
                f"🎉 <b>مبروك!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{cur()} <b>+{fmt(amount)}</b> نقطة!\n"
                f"📊 رصيدك الجديد: <b>{fmt(new_ud.get('points', 0))}</b>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(msg)

    if is_new and ref:
        rp = s().get("referral_points", 5)
        db.add_points(ref, rp)
        ru = db.get_user(ref)
        db.save_user(ref, {"total_referrals": ru.get("total_referrals", 0) + 1})
        try:
            await context.bot.send_message(ref,
                f"🎉 <b>عضو جديد عبر رابطك!</b>\n\n"
                f"{cur()} مكسبك: <b>+{rp}</b> نقطة\n"
                f"📊 رصيدك: <b>{fmt(ru.get('points',0)+rp)}</b>",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass

    if is_new and not is_admin(user.id):
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(aid,
                    f"🆕 <b>مستخدم جديد</b>\n"
                    f"👤 {esc(user.first_name)}\n"
                    f"🔗 @{user.username or '—'}\n"
                    f"🆔 <code>{user.id}</code>",
                    parse_mode=ParseMode.HTML)
            except Exception:
                pass

    if ud.get("is_banned") and not is_admin(user.id):
        await update.message.reply_text("🚫 أنت محظور")
        return

    ud = db.get_user(user.id)
    await update.message.reply_text(
        f"{s().get('welcome')}\n\n"
        f"{cur()} رصيدك: <b>{fmt(ud.get('points', 0))}</b>",
        reply_markup=main_menu_kb(user.id),
        parse_mode=ParseMode.HTML,
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await show_panel(update.message)


async def show_panel(msg, edit=False):
    total_u = db.get_total_users()
    total_p = len(db.get_products(active_only=False))
    st = db.get_stats()
    mt = db.is_maintenance_active()
    ch_count = len(db.get_required_channels())
    text = (
        f"⚙️ <b>لوحة التحكم</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: <b>{total_u}</b>\n"
        f"📦 المنتجات: <b>{total_p}</b>\n"
        f"🛒 المبيعات: <b>{st.get('total_sales', 0)}</b>\n"
        f"📣 قنوات الاشتراك: <b>{ch_count}</b>\n"
        f"🔧 الصيانة: <b>{'🔴 نشطة' if mt else '🟢 معطلة'}</b>"
    )
    if edit:
        try:
            await msg.edit_text(text, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)
        except Exception:
            await msg.reply_text(text, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)
    else:
        await msg.reply_text(text, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════
#   Global Callbacks
# ═══════════════════════════════════════════════════════════
async def cb_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    is_sub, missing = await check_subscription(q.from_user.id, context)
    if is_sub:
        ud = db.get_user(q.from_user.id)
        if not ud:
            ud, _ = db.register_user(q.from_user.id, q.from_user.first_name or "", q.from_user.username or "")
        await q.edit_message_text(
            f"✅ <b>تم التحقق من الاشتراك!</b>\n\n"
            f"{s().get('welcome')}\n\n"
            f"{cur()} رصيدك: <b>{fmt(ud.get('points', 0))}</b>",
            reply_markup=main_menu_kb(q.from_user.id),
            parse_mode=ParseMode.HTML,
        )
    else:
        await q.answer("❌ لم تشترك بعد!", show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=subscription_kb(missing))
        except Exception:
            pass


async def cb_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data == "back_main":
        await q.answer()
        if not await require_subscription(update, context):
            return
        ud = db.get_user(q.from_user.id)
        await q.edit_message_text(
            f"{s().get('welcome')}\n\n"
            f"{cur()} رصيدك: <b>{fmt(ud.get('points', 0))}</b>",
            reply_markup=main_menu_kb(q.from_user.id),
            parse_mode=ParseMode.HTML,
        )
        return
    if data == "admin_panel":
        await q.answer()
        if not is_admin(q.from_user.id): return
        await show_panel(q.message, edit=True)
        return
    if data == "noop":
        await q.answer()
        return


# ═══════════════════════════════════════════════════════════
#   User Callbacks
# ═══════════════════════════════════════════════════════════
async def cb_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    ud = db.get_user(q.from_user.id)
    await q.edit_message_text(
        f"{cur()} <b>رصيدك:</b> {fmt(ud.get('points', 0))} نقطة",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]),
        parse_mode=ParseMode.HTML,
    )


async def cb_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    products = db.get_products(active_only=True)
    if not products:
        await q.edit_message_text(
            "🛍️ <b>المتجر</b>\n\n📭 لا توجد منتجات",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]),
            parse_mode=ParseMode.HTML,
        )
        return
    ud = db.get_user(q.from_user.id)
    await q.edit_message_text(
        f"🛍️ <b>المتجر</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{cur()} رصيدك: <b>{fmt(ud.get('points', 0))}</b>\n\n👇 اختر:",
        reply_markup=shop_kb(),
        parse_mode=ParseMode.HTML,
    )


async def cb_view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    pid = q.data.replace("view_", "")
    p = db.get_product(pid)
    if not p or not p.get("active", True):
        await q.answer("❌ غير متاح", show_alert=True); return
    ud = db.get_user(q.from_user.id)
    balance = ud.get("points", 0)
    price = p.get("price", 0)
    avail = db.is_product_available(pid)
    if not avail:
        status = "❌ نفدت الكمية"
    elif balance >= price:
        status = "✅ يمكنك الشراء"
    else:
        status = f"❌ ينقصك {fmt(price - balance)}"
    await q.edit_message_text(
        f"{p.get('emoji','')} <b>{esc(p.get('name',''))}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 {esc(p.get('description') or '—')}\n\n"
        f"{cur()} <b>السعر:</b> {fmt(price)} نقطة\n"
        f"{stock_label(pid)}\n"
        f"💼 <b>رصيدك:</b> {fmt(balance)}\n"
        f"{status}",
        reply_markup=product_kb(pid),
        parse_mode=ParseMode.HTML,
    )


async def cb_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    pid = q.data.replace("buy_", "")
    p = db.get_product(pid)
    ud = db.get_user(q.from_user.id)
    if not p or not p.get("active", True):
        await q.answer("❌ غير متاح", show_alert=True); return
    if not db.is_product_available(pid):
        await q.answer("❌ نفدت الكمية", show_alert=True); return
    price = p.get("price", 0)
    if ud.get("points", 0) < price:
        await q.answer(f"❌ ينقصك {fmt(price - ud.get('points', 0))}", show_alert=True); return
    if not db.remove_points(q.from_user.id, price):
        await q.answer("❌ فشل الخصم", show_alert=True); return
    content_item = db.get_available_content(pid)
    if not content_item:
        db.add_points(q.from_user.id, price)
        await q.answer("❌ نفدت", show_alert=True); return
    db.increment_sold(pid)
    oid = f"o{int(datetime.now().timestamp())}"
    db.add_order(oid, {
        "order_id": oid, "user_id": q.from_user.id, "product_id": pid,
        "product_name": p.get("name", "?"), "price": price,
        "date": int(datetime.now().timestamp()),
    })
    purchases = ud.get("purchases", [])
    purchases.append({"pid": pid, "date": int(datetime.now().timestamp())})
    db.save_user(q.from_user.id, {
        "purchases": purchases, "total_spent": ud.get("total_spent", 0) + price,
    })
    await deliver(context.bot, q.from_user.id, content_item, p)
    nu = db.get_user(q.from_user.id)
    try:
        await notify_admins_purchase(context, q.from_user, p, price, nu.get("points", 0))
    except Exception as e:
        logger.warning(f"Notify: {e}")
    try:
        remaining = db.get_product_stock(pid)
        await post_proof(context, q.from_user, p, price, remaining)
    except Exception as e:
        logger.warning(f"Proof: {e}")
    await q.edit_message_text(
        f"✅ <b>تم الشراء!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {p.get('emoji','')} <b>{esc(p.get('name',''))}</b>\n"
        f"💸 {fmt(price)} نقطة\n"
        f"{cur()} رصيدك: <b>{fmt(nu.get('points', 0))}</b>\n"
        f"{stock_label(pid)}\n\n"
        f"📩 تحقق من الرسالة أعلاه",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ المتجر", callback_data="shop")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_main")],
        ]),
        parse_mode=ParseMode.HTML,
    )


async def deliver(bot, uid, content, product):
    ctype = content.get("type", "text")
    data = content.get("data", "")
    cap = content.get("caption", "")
    header = f"{product.get('emoji','')} <b>{esc(product.get('name',''))}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    try:
        if ctype == "text":
            await bot.send_message(uid, header + data, parse_mode=ParseMode.HTML)
        elif ctype == "link":
            await bot.send_message(uid, header + f"🔗 {data}",
                parse_mode=ParseMode.HTML, disable_web_page_preview=False)
        elif ctype == "photo":
            await bot.send_photo(uid, photo=data,
                caption=(header + cap) if cap else header, parse_mode=ParseMode.HTML)
        elif ctype == "video":
            await bot.send_video(uid, video=data,
                caption=(header + cap) if cap else header, parse_mode=ParseMode.HTML)
        elif ctype == "document":
            await bot.send_document(uid, document=data,
                caption=(header + cap) if cap else header, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"deliver: {e}")


async def cb_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    ud = db.get_user(q.from_user.id)
    gift = s().get("daily_gift_points", 10)
    cd = s().get("daily_gift_cooldown", 86400)
    last = ud.get("last_gift", 0)
    now = int(datetime.now().timestamp())
    diff = now - last
    if last > 0 and diff < cd:
        rem = cd - diff
        await q.edit_message_text(
            f"🎁 <b>الهدية</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❌ استلمت مسبقاً\n\n"
            f"⏳ المتبقي: <b>{fmt_rem(rem)}</b>\n"
            f"🎁 القادمة: +{fmt(gift)} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]),
            parse_mode=ParseMode.HTML,
        )
        return
    db.add_points(q.from_user.id, gift)
    db.save_user(q.from_user.id, {"last_gift": now})
    nu = db.get_user(q.from_user.id)
    await q.edit_message_text(
        f"🎉 <b>مبروك!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 +{fmt(gift)} نقطة\n"
        f"{cur()} رصيدك: <b>{fmt(nu.get('points',0))}</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]),
        parse_mode=ParseMode.HTML,
    )


async def cb_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    ud = db.get_user(q.from_user.id)
    code = ud.get("referral_code", "—")
    link = f"https://t.me/{context.bot.username}?start={code}"
    rp = s().get("referral_points", 5)
    await q.edit_message_text(
        f"👥 <b>دعوة الأصدقاء</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"📊 إحالاتك: <b>{ud.get('total_referrals',0)}</b>\n"
        f"{cur()} نقاطك: <b>{fmt(ud.get('points',0))}</b>\n\n"
        f"💡 كل صديق = <b>+{fmt(rp)}</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 مشاركة",
                url=f"https://t.me/share/url?url={link}&text=انضم")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")],
        ]),
        parse_mode=ParseMode.HTML,
    )


async def cb_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await require_subscription(update, context): return
    orders = db.get_user_orders(q.from_user.id)
    if not orders:
        text = "🎒 <b>مشترياتي</b>\n\n📭 لا شيء"
    else:
        text = f"🎒 <b>مشترياتي ({len(orders)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for o in orders[-10:]:
            d = datetime.fromtimestamp(o.get("date", 0)).strftime("%Y-%m-%d %H:%M")
            text += f"📦 <b>{esc(o.get('product_name', '?'))}</b>\n"
            text += f"   💸 {fmt(o.get('price', 0))} | 📅 {d}\n\n"
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════
#   Admin Callbacks
# ═══════════════════════════════════════════════════════════
async def cb_adm_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    st = db.get_stats()
    top = db.get_top_users(5)
    tr = db.get_top_referrers(5)
    text = (
        f"📊 <b>الإحصائيات</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: <b>{st.get('total_users', 0)}</b>\n"
        f"📦 المنتجات: <b>{st.get('total_products', 0)}</b>\n"
        f"🛒 المبيعات: <b>{st.get('total_sales', 0)}</b>\n"
        f"💎 إجمالي النقاط: <b>{fmt(st.get('total_points_given', 0))}</b>\n\n"
        f"🏆 <b>أغنى 5:</b>\n"
    )
    for i, u in enumerate(top, 1):
        text += f"{i}. {esc(u.get('first_name','?'))} — {fmt(u.get('points',0))}\n"
    text += f"\n🥇 <b>أفضل المحيلين:</b>\n"
    for i, u in enumerate(tr, 1):
        text += f"{i}. {esc(u.get('first_name','?'))} — {u.get('total_referrals',0)}\n"
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")]]),
        parse_mode=ParseMode.HTML,
    )


async def cb_adm_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    products = db.get_products(active_only=False)
    if not products:
        await q.edit_message_text(
            "📭 لا توجد منتجات",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة", callback_data="adm_add_p")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        return
    keyboard = []
    for pid, p in products.items():
        active = "🟢" if p.get("active", True) else "🔴"
        keyboard.append([InlineKeyboardButton(
            f"{active} {p.get('emoji','')} {p.get('name','?')} — {fmt(p.get('price',0))}",
            callback_data=f"editp_{pid}"
        )])
    keyboard.append([InlineKeyboardButton("➕ إضافة منتج", callback_data="adm_add_p")])
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
    await q.edit_message_text(
        f"📦 <b>المنتجات ({len(products)})</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def cb_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    pid = q.data.replace("editp_", "")
    p = db.get_product(pid)
    if not p:
        await q.answer("❌ غير موجود", show_alert=True); return ConversationHandler.END
    context.user_data["edit_pid"] = pid
    mode = p.get("delivery_mode", "single")
    mode_text = "♾️ لا نهائي" if mode == "single" else "📚 متعدد"
    count = len(p.get("contents", [])) if mode == "multi" else (1 if p.get("content") else 0)
    active = "🟢" if p.get("active", True) else "🔴"
    text = (
        f"✏️ <b>{p.get('emoji','')} {esc(p.get('name',''))}</b> {active}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {esc((p.get('description') or '—')[:50])}\n"
        f"💰 {fmt(p.get('price', 0))}\n"
        f"🎯 {mode_text}\n"
        f"📊 {stock_label(pid)}\n"
        f"📦 عناصر: <b>{count}</b>\n"
    )
    keyboard = [
        [InlineKeyboardButton("📝 الاسم", callback_data="epf_name"),
         InlineKeyboardButton("😀 الإيموجي", callback_data="epf_emoji")],
        [InlineKeyboardButton("📄 الوصف", callback_data="epf_desc"),
         InlineKeyboardButton("💰 السعر", callback_data="epf_price")],
    ]
    if mode == "multi":
        keyboard.append([InlineKeyboardButton(
            f"📦 إدارة المحتوى ({count})",
            callback_data=f"mngc_{pid}"
        )])
    else:
        keyboard.append([InlineKeyboardButton("📦 تعديل المحتوى", callback_data="epf_content")])
    keyboard += [
        [InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"togglep_{pid}")],
        [InlineKeyboardButton("🗑️ حذف", callback_data=f"delp_{pid}")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="adm_products")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return PE_VALUE


async def cb_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "adm_products":
        await q.answer()
        await cb_adm_products(update, context)
        return ConversationHandler.END
    if q.data.startswith("togglep_") or q.data.startswith("delp_"):
        return ConversationHandler.END
    await q.answer()
    field = q.data.replace("epf_", "")
    context.user_data["edit_field"] = field
    names = {"name": "📝 الاسم", "emoji": "😀 الإيموجي",
             "desc": "📄 الوصف", "price": "💰 السعر",
             "content": "📦 المحتوى"}
    await q.edit_message_text(
        f"✏️ أرسل <b>{names.get(field, field)}</b> الجديد:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return PE_VALUE


async def pe_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()
    field = context.user_data.get("edit_field")
    pid = context.user_data.get("edit_pid")
    if not field or not pid:
        return ConversationHandler.END
    if field == "price":
        try:
            v = int(v)
            if v < 0: raise ValueError
        except Exception:
            await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
            return PE_VALUE
    if db.update_product(pid, {field: v}):
        await update.message.reply_text(
            "✅ تم التحديث!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ تعديل المزيد", callback_data=f"editp_{pid}")],
                [InlineKeyboardButton("📦 المنتجات", callback_data="adm_products")],
            ]),
        )
    else:
        await update.message.reply_text("❌ فشل")
    return ConversationHandler.END


async def cb_toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = q.data.replace("togglep_", "")
    p = db.get_product(pid)
    if not p:
        await q.answer("❌ غير موجود", show_alert=True); return
    new_active = not p.get("active", True)
    db.update_product(pid, {"active": new_active})
    await q.answer(f"{'🟢 مفعل' if new_active else '🔴 معطل'}", show_alert=True)
    await cb_edit_product(update, context)


async def cb_delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("delp_", "")
    p = db.get_product(pid)
    if not p: return
    db.backup()
    db.delete_product(pid)
    await q.edit_message_text(
        f"✅ تم حذف <b>{esc(p.get('name','?'))}</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 المنتجات", callback_data="adm_products")]
        ]),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════
#   Manage Content
# ═══════════════════════════════════════════════════════════
async def cb_manage_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("mngc_", "")
    p = db.get_product(pid)
    if not p: return ConversationHandler.END
    context.user_data["mng_pid"] = pid
    contents = p.get("contents", [])
    keyboard = []
    for i, c in enumerate(contents[:20]):
        ctype = c.get("type", "text")
        preview = (c.get("data", "")[:30] if ctype == "text" else ctype)
        keyboard.append([InlineKeyboardButton(
            f"🗑️ #{i+1} — {preview}",
            callback_data=f"delc_{i}"
        )])
    keyboard.append([InlineKeyboardButton("➕ إضافة محتوى", callback_data=f"addc_{pid}")])
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data=f"editp_{pid}")])
    sold = p.get("sold_count", 0)
    rem = max(0, len(contents) - sold)
    await q.edit_message_text(
        f"📦 <b>إدارة محتوى: {esc(p.get('name','?'))}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 إجمالي: <b>{len(contents)}</b>\n"
        f"🛒 مبيع: <b>{sold}</b>\n"
        f"📊 متبقي: <b>{rem}</b>\n\n"
        f"👇 اختر:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return PE_VALUE


async def cb_del_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    idx = int(q.data.replace("delc_", ""))
    pid = context.user_data.get("mng_pid")
    if pid:
        db.remove_content_from_product(pid, idx)
        await q.answer("✅ حذف", show_alert=True)
    await cb_manage_content(update, context)
    return PE_VALUE


async def cb_add_content_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("addc_", "")
    context.user_data["addc_pid"] = pid
    await q.edit_message_text(
        "➕ <b>إضافة محتوى</b>\n\n🎯 اختر النوع:",
        reply_markup=cancel_kb([
            [InlineKeyboardButton("📝 نص", callback_data="ctext_text"),
             InlineKeyboardButton("🔗 رابط", callback_data="ctext_link")],
            [InlineKeyboardButton("📸 صورة", callback_data="ctext_photo"),
             InlineKeyboardButton("🎬 فيديو", callback_data="ctext_video")],
            [InlineKeyboardButton("📎 ملف", callback_data="ctext_document")],
        ]),
        parse_mode=ParseMode.HTML,
    )
    return AC_CONTENT


async def ac_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q and q.data.startswith("ctext_"):
        await q.answer()
        ctype = q.data.replace("ctext_", "")
        context.user_data["ac_type"] = ctype
        hints = {
            "text": "📝 أرسل النص",
            "link": "🔗 أرسل الرابط",
            "photo": "📸 أرسل صورة",
            "video": "🎬 أرسل فيديو",
            "document": "📎 أرسل ملف",
        }
        await q.edit_message_text(
            f"{hints.get(ctype)}:",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_only_kb(),
        )
        return AC_CONTENT
    msg = update.message
    pid = context.user_data.get("addc_pid")
    ctype = context.user_data.get("ac_type")
    if not pid or not ctype:
        return ConversationHandler.END
    data, cap = "", ""
    if ctype == "text":
        data = msg.text or ""
    elif ctype == "link":
        data = msg.text or ""
    elif ctype == "photo":
        if not msg.photo:
            await msg.reply_text("❌ أرسل صورة", reply_markup=cancel_only_kb()); return AC_CONTENT
        data = msg.photo[-1].file_id; cap = msg.caption or ""
    elif ctype == "video":
        if not msg.video:
            await msg.reply_text("❌ أرسل فيديو", reply_markup=cancel_only_kb()); return AC_CONTENT
        data = msg.video.file_id; cap = msg.caption or ""
    elif ctype == "document":
        if not msg.document:
            await msg.reply_text("❌ أرسل ملف", reply_markup=cancel_only_kb()); return AC_CONTENT
        data = msg.document.file_id; cap = msg.caption or ""
    if not data:
        await msg.reply_text("❌ فارغ", reply_markup=cancel_only_kb()); return AC_CONTENT
    item = {"type": ctype, "data": data}
    if cap: item["caption"] = cap
    if db.add_content_to_product(pid, item):
        p = db.get_product(pid)
        await msg.reply_text(
            f"✅ تم الإضافة\n\n📦 {esc(p.get('name','?'))}\n"
            f"📚 إجمالي: <b>{len(p.get('contents', []))}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ آخر", callback_data=f"addc_{pid}")],
                [InlineKeyboardButton("📦 إدارة", callback_data=f"mngc_{pid}")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.reply_text("❌ فشل")
    context.user_data.pop("ac_type", None)
    context.user_data.pop("addc_pid", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Add Product
# ═══════════════════════════════════════════════════════════
async def adm_add_p_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    context.user_data["new_p"] = {}
    await q.edit_message_text(
        "➕ <b>إضافة منتج جديد</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>1/6</b> — اسم المنتج",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return P_NAME


async def p_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not t:
        await update.message.reply_text("❌ فارغ", reply_markup=cancel_only_kb()); return P_NAME
    context.user_data["new_p"]["name"] = t
    await update.message.reply_text(
        f"✅ <b>{esc(t)}</b>\n\n😀 <b>2/6</b> — الإيموجي (أو <code>-</code>)",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return P_EMOJI


async def p_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    context.user_data["new_p"]["emoji"] = "📦" if t == "-" else t
    await update.message.reply_text(
        f"✅\n\n📄 <b>3/6</b> — الوصف (أو <code>-</code>)",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return P_DESC


async def p_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    context.user_data["new_p"]["description"] = "" if t == "-" else t
    await update.message.reply_text(
        f"✅\n\n💰 <b>4/6</b> — السعر بالـ نقاط",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return P_PRICE


async def p_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = int(update.message.text.strip())
        if p < 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
        return P_PRICE
    context.user_data["new_p"]["price"] = p
    await update.message.reply_text(
        f"✅ <b>{fmt(p)}</b>\n\n🎯 <b>5/6</b> — نوع التسليم:",
        reply_markup=cancel_kb([
            [InlineKeyboardButton("♾️ محتوى واحد (لا نهائي)", callback_data="pmode_single")],
            [InlineKeyboardButton("📚 محتوى متعدد (مخزون)", callback_data="pmode_multi")],
        ]),
        parse_mode=ParseMode.HTML,
    )
    return P_MODE


async def p_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    mode = "single" if q.data == "pmode_single" else "multi"
    context.user_data["new_p"]["delivery_mode"] = mode
    prefix = "pct_" if mode == "single" else "mct_"
    label = "♾️ واحد" if mode == "single" else "📚 متعدد"
    await q.edit_message_text(
        f"✅ {label}\n\n📦 <b>6/6</b> — نوع العنصر الأول:",
        reply_markup=cancel_kb([
            [InlineKeyboardButton("📝 نص", callback_data=f"{prefix}text")],
            [InlineKeyboardButton("🔗 رابط", callback_data=f"{prefix}link")],
            [InlineKeyboardButton("📸 صورة", callback_data=f"{prefix}photo")],
            [InlineKeyboardButton("🎬 فيديو", callback_data=f"{prefix}video")],
            [InlineKeyboardButton("📎 ملف", callback_data=f"{prefix}document")],
        ]),
        parse_mode=ParseMode.HTML,
    )
    return P_FIRST_CONTENT


async def p_first_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q and (q.data.startswith("pct_") or q.data.startswith("mct_")):
        await q.answer()
        prefix = "pct_" if q.data.startswith("pct_") else "mct_"
        ctype = q.data.replace(prefix, "")
        context.user_data["first_ctype"] = ctype
        hints = {
            "text": "📝 أرسل النص",
            "link": "🔗 أرسل الرابط",
            "photo": "📸 أرسل صورة",
            "video": "🎬 أرسل فيديو",
            "document": "📎 أرسل ملف",
        }
        await q.edit_message_text(
            f"{hints.get(ctype)}:",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_only_kb(),
        )
        return P_FIRST_CONTENT
    msg = update.message
    data = context.user_data.get("new_p", {})
    ctype = context.user_data.get("first_ctype")
    mode = data.get("delivery_mode", "single")
    cd, cap = "", ""
    if ctype == "text":
        cd = msg.text or ""
    elif ctype == "link":
        cd = msg.text or ""
    elif ctype == "photo":
        if not msg.photo:
            await msg.reply_text("❌ أرسل صورة", reply_markup=cancel_only_kb()); return P_FIRST_CONTENT
        cd = msg.photo[-1].file_id; cap = msg.caption or ""
    elif ctype == "video":
        if not msg.video:
            await msg.reply_text("❌ أرسل فيديو", reply_markup=cancel_only_kb()); return P_FIRST_CONTENT
        cd = msg.video.file_id; cap = msg.caption or ""
    elif ctype == "document":
        if not msg.document:
            await msg.reply_text("❌ أرسل ملف", reply_markup=cancel_only_kb()); return P_FIRST_CONTENT
        cd = msg.document.file_id; cap = msg.caption or ""
    if not cd:
        await msg.reply_text("❌ فارغ", reply_markup=cancel_only_kb()); return P_FIRST_CONTENT
    if mode == "single":
        data["content"] = {"type": ctype, "data": cd}
        if cap: data["content"]["caption"] = cap
        data["contents"] = []
    else:
        item = {"type": ctype, "data": cd}
        if cap: item["caption"] = cap
        data["contents"] = [item]
        data["content"] = {}
    data["active"] = True
    pid = f"p{int(datetime.now().timestamp())}"
    if db.add_product(pid, data):
        if mode == "single":
            await msg.reply_text(
                f"✅ <b>تم!</b>\n\n{data.get('emoji','')} <b>{esc(data.get('name',''))}</b>\n"
                f"💰 {fmt(data.get('price', 0))}\n🎯 ♾️ لا نهائي\n🆔 <code>{pid}</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ آخر", callback_data="adm_add_p")],
                    [InlineKeyboardButton("📦 المنتجات", callback_data="adm_products")],
                ]),
                parse_mode=ParseMode.HTML,
            )
        else:
            await msg.reply_text(
                f"✅ <b>تم (محتوى متعدد)</b>\n\n{data.get('emoji','')} <b>{esc(data.get('name',''))}</b>\n"
                f"💰 {fmt(data.get('price', 0))}\n📚 عناصر: <b>1</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ إضافة عناصر", callback_data=f"addc_{pid}")],
                    [InlineKeyboardButton("📦 المنتجات", callback_data="adm_products")],
                ]),
                parse_mode=ParseMode.HTML,
            )
    else:
        await msg.reply_text("❌ فشل")
    context.user_data.pop("new_p", None)
    context.user_data.pop("first_ctype", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Points Links
# ═══════════════════════════════════════════════════════════
async def cb_adm_pl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    links = db.get_points_links()
    if not links:
        text = (
            "🎁 <b>روابط النقاط</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📭 لا توجد روابط بعد\n\n"
            "💡 أنشئ رابطاً وشاركه ليحصل المستخدمون على نقاط مجاناً"
        )
    else:
        text = f"🎁 <b>روابط النقاط ({len(links)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for code, link in list(links.items())[:10]:
            valid, reason = db.is_points_link_valid(link)
            status = "🟢" if valid else f"🔴 ({reason})"
            amount = link.get("amount", 0)
            uses = link.get("uses", 0)
            max_uses = link.get("max_uses", 0)
            uses_str = f"{uses}/{max_uses}" if max_uses > 0 else f"{uses}/♾️"
            text += f"{status} <code>{code}</code>\n"
            text += f"   💰 {fmt(amount)} | 👥 {uses_str}\n\n"
    keyboard = [
        [InlineKeyboardButton("➕ إنشاء رابط", callback_data="pl_create")],
        [InlineKeyboardButton("📋 عرض الكل", callback_data="pl_list")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def cb_pl_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    links = db.get_points_links()
    if not links:
        await q.answer("📭 لا توجد روابط", show_alert=True)
        return
    text = f"📋 <b>كل الروابط ({len(links)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for code, link in list(links.items())[:20]:
        valid, reason = db.is_points_link_valid(link)
        status = "🟢" if valid else "🔴"
        amount = link.get("amount", 0)
        uses = link.get("uses", 0)
        text += f"{status} <code>{code}</code> — {fmt(amount)} نقطة | {uses} استخدام\n"
    keyboard = []
    for code in list(links.keys())[:20]:
        keyboard.append([InlineKeyboardButton(
            f"🗑️ حذف {code}",
            callback_data=f"pl_del_{code}"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="adm_pl")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def cb_pl_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    code = q.data.replace("pl_del_", "")
    if db.delete_points_link(code):
        await q.answer("✅ تم الحذف", show_alert=True)
    else:
        await q.answer("❌ فشل", show_alert=True)
    await cb_pl_list(update, context)


async def adm_pl_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    context.user_data["new_pl"] = {}
    await q.edit_message_text(
        "🎁 <b>إنشاء رابط نقاط</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>1/3</b> — أرسل <b>عدد النقاط</b> لكل مستخدم\n\n"
        "💡 مثال: <code>50</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return PL_AMOUNT


async def pl_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        am = int(update.message.text.strip())
        if am <= 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
        return PL_AMOUNT
    context.user_data["new_pl"]["amount"] = am
    await update.message.reply_text(
        f"✅ النقاط: <b>{fmt(am)}</b>\n\n"
        f"👥 <b>2/3</b> — أرسل <b>الحد الأقصى للاستخدامات</b>\n\n"
        f"💡 <code>0</code> = بلا حدود",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return PL_MAX_USES


async def pl_max_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mu = int(update.message.text.strip())
        if mu < 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
        return PL_MAX_USES
    context.user_data["new_pl"]["max_uses"] = mu
    uses_text = "♾️ بلا حدود" if mu == 0 else f"{mu}"
    await update.message.reply_text(
        f"✅ الاستخدامات: <b>{uses_text}</b>\n\n"
        f"⏰ <b>3/3</b> — أرسل <b>مدة الصلاحية بالساعات</b>\n\n"
        f"💡 <code>0</code> = بلا انتهاء",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return PL_EXPIRE_HOURS


async def pl_expire_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        h = int(update.message.text.strip())
        if h < 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
        return PL_EXPIRE_HOURS
    data = context.user_data.get("new_pl", {})
    data["expire_hours"] = h
    code = "PTS_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    while db.get_points_link(code):
        code = "PTS_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expire_at = 0
    if h > 0:
        expire_at = int(datetime.now().timestamp()) + (h * 3600)
    link_data = {
        "amount": data.get("amount", 0),
        "max_uses": data.get("max_uses", 0),
        "expire_at": expire_at,
        "created_by": update.effective_user.id,
    }
    if db.add_points_link(code, link_data):
        bot_username = context.bot.username
        full_link = f"https://t.me/{bot_username}?start={code}"
        share_text = f"🎁 احصل على {data.get('amount',0)} نقطة مجاناً!"
        share_url = f"https://t.me/share/url?url={full_link}&text={share_text}"
        uses_text = "♾️" if data.get("max_uses", 0) == 0 else str(data.get("max_uses", 0))
        expire_text = "♾️" if h == 0 else f"{h} ساعة"
        await update.message.reply_text(
            f"✅ <b>تم إنشاء الرابط!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 <code>{full_link}</code>\n\n"
            f"💰 <b>النقاط:</b> {fmt(data.get('amount', 0))}\n"
            f"👥 <b>الاستخدامات:</b> {uses_text}\n"
            f"⏰ <b>الصلاحية:</b> {expire_text}\n\n"
            f"💡 شارك الرابط وسيحصل من يدخله على النقاط",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 مشاركة", url=share_url)],
                [InlineKeyboardButton("➕ رابط آخر", callback_data="pl_create")],
                [InlineKeyboardButton("📋 القائمة", callback_data="adm_pl")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ فشل إنشاء الرابط")
    context.user_data.pop("new_pl", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Channels Management
# ═══════════════════════════════════════════════════════════
async def cb_adm_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    channels = db.get_required_channels()
    if not channels:
        text = (
            "📣 <b>قنوات الاشتراك الإجباري</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📭 لا توجد قنوات مضافة"
        )
    else:
        text = f"📣 <b>قنوات الاشتراك ({len(channels)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, ch in enumerate(channels, 1):
            text += f"{i}. <b>{esc(ch.get('title','?'))}</b>\n"
            text += f"   🆔 <code>{ch.get('chat_id','?')}</code>\n\n"
    keyboard = [[InlineKeyboardButton("➕ إضافة قناة", callback_data="add_ch")]]
    for ch in channels:
        keyboard.append([InlineKeyboardButton(
            f"🗑️ حذف {esc(ch.get('title','?'))}",
            callback_data=f"delch_{ch.get('chat_id','')}"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def cb_del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    chat_id = q.data.replace("delch_", "")
    if db.remove_required_channel(chat_id):
        await q.answer("✅ تم الحذف", show_alert=True)
    else:
        await q.answer("❌ فشل", show_alert=True)
    await cb_adm_channels(update, context)


async def adm_add_ch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "➕ <b>إضافة قناة للاشتراك الإجباري</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 أرسل <b>معرّف القناة</b> أو <b>ID</b>:\n\n"
        "💡 أمثلة:\n"
        "• <code>@my_channel</code>\n"
        "• <code>-1001234567890</code>\n\n"
        "⚠️ <b>البوت يجب أن يكون مشرفاً في القناة!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return ADD_CH_ID


async def add_ch_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text.strip()
    context.user_data["new_ch_id"] = chat_id
    try:
        chat = await context.bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
        context.user_data["new_ch_title"] = title
        url = f"https://t.me/{chat.username}" if chat.username else ""
        context.user_data["new_ch_url"] = url
        try:
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                await update.message.reply_text(
                    f"⚠️ <b>البوت ليس مشرفاً!</b>",
                    parse_mode=ParseMode.HTML,
                )
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"❌ {esc(str(e))}", parse_mode=ParseMode.HTML)
            return ConversationHandler.END
        await update.message.reply_text(
            f"✅ <b>{esc(title)}</b>\n🆔 <code>{chat_id}</code>\n\n"
            f"📝 أرسل <b>اسم القناة</b> (أو <code>-</code>)",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_only_kb(),
        )
        return ADD_CH_TITLE
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>فشل الوصول</b>\n\n<code>{esc(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END


async def add_ch_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    title = context.user_data.get("new_ch_title", "قناة") if t == "-" else t
    chat_id = context.user_data.get("new_ch_id")
    url = context.user_data.get("new_ch_url", "")
    if db.add_required_channel(chat_id, title, url):
        await update.message.reply_text(
            f"✅ <b>تم إضافة القناة!</b>\n\n📢 {esc(title)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📣 القنوات", callback_data="adm_channels")],
                [InlineKeyboardButton("⚙️ اللوحة", callback_data="admin_panel")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ فشل أو القناة موجودة مسبقاً")
    context.user_data.clear()
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Users / Give / Ban / Message / Broadcast
# ═══════════════════════════════════════════════════════════
async def cb_adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    users = db.get_all_users()
    if not users:
        text = "📭 لا يوجد مستخدمون"
    else:
        su = sorted(users.values(), key=lambda u: u.get("joined_at", 0), reverse=True)[:20]
        text = f"👥 <b>المستخدمون ({len(users)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for u in su:
            b = "🚫" if u.get("is_banned") else ""
            text += f"{b}👤 <b>{esc(u.get('first_name','?'))}</b>\n"
            text += f"   🆔 <code>{u.get('user_id','?')}</code> | {cur()} {fmt(u.get('points',0))}\n\n"
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")]]),
        parse_mode=ParseMode.HTML,
    )


async def adm_give_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "💰 أرسل <b>ID المستخدم</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return UP_USER


async def up_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ ID غير صحيح", reply_markup=cancel_only_kb()); return UP_USER
    u = db.get_user(uid)
    if not u:
        await update.message.reply_text("❌ غير موجود", reply_markup=cancel_only_kb()); return UP_USER
    context.user_data["give_uid"] = uid
    await update.message.reply_text(
        f"✅ {esc(u.get('first_name','?'))}\n"
        f"{cur()} رصيده: {fmt(u.get('points',0))}\n\n"
        f"💰 أرسل العدد (سالب للخصم)",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return UP_AMOUNT


async def up_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        am = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb()); return UP_AMOUNT
    uid = context.user_data.get("give_uid")
    if not uid: return ConversationHandler.END
    db.add_points(uid, am)
    nu = db.get_user(uid)
    await update.message.reply_text(
        f"✅ {esc(nu.get('first_name','?'))}\n"
        f"{cur()} رصيده: <b>{fmt(nu.get('points',0))}</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ اللوحة", callback_data="admin_panel")]]),
        parse_mode=ParseMode.HTML,
    )
    try:
        if am > 0:
            await context.bot.send_message(uid,
                f"🎁 تم إضافة <b>{fmt(am)}</b> نقطة!\n"
                f"{cur} رصيدك: <b>{fmt(nu.get('points',0))}</b>",
                parse_mode=ParseMode.HTML)
    except Exception:
        pass
    return ConversationHandler.END


async def adm_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "🔨 أرسل <b>ID المستخدم</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return UB_USER


async def ub_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ ID غير صحيح", reply_markup=cancel_only_kb()); return UB_USER
    u = db.get_user(uid)
    if not u:
        await update.message.reply_text("❌ غير موجود", reply_markup=cancel_only_kb()); return UB_USER
    new = not u.get("is_banned", False)
    db.ban_user(uid, new)
    await update.message.reply_text(
        f"✅ <code>{uid}</code> أصبح <b>{'محظور' if new else 'غير محظور'}</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ اللوحة", callback_data="admin_panel")]]),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def adm_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "💬 أرسل <b>ID المستخدم</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return MSG_USER


async def msg_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ ID غير صحيح", reply_markup=cancel_only_kb()); return MSG_USER
    context.user_data["msg_uid"] = uid
    await update.message.reply_text("💬 أرسل الرسالة:", reply_markup=cancel_only_kb())
    return MSG_TEXT


async def msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("msg_uid")
    if not uid: return ConversationHandler.END
    try:
        await context.bot.send_message(uid,
            f"📩 <b>رسالة من الإدارة</b>\n\n{update.message.text}",
            parse_mode=ParseMode.HTML)
        await update.message.reply_text(
            "✅ تم الإرسال",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ اللوحة", callback_data="admin_panel")]]),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
    return ConversationHandler.END


async def adm_bc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "📢 أرسل رسالة البث",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return BC_TEXT


async def bc_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    users = db.get_all_users()
    await update.message.reply_text(f"📤 جاري الإرسال لـ {len(users)}...")
    ok, fl = 0, 0
    for u in users.values():
        try:
            await context.bot.send_message(u.get("user_id"),
                f"📢 <b>إعلان</b>\n\n{text}", parse_mode=ParseMode.HTML)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fl += 1
    await update.message.reply_text(
        f"✅ انتهى\n✔️ {ok} | ❌ {fl}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ اللوحة", callback_data="admin_panel")]]),
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Maintenance
# ═══════════════════════════════════════════════════════════
async def cb_adm_maint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    m = db.get_maintenance()
    active = m.get("active", False)
    text = (
        f"🔧 <b>الصيانة</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالة: <b>{'🔴 نشطة' if active else '🟢 معطلة'}</b>\n\n"
        f"📝 <code>{esc(m.get('message','—'))}</code>\n"
    )
    end = m.get("end_time", 0)
    if end > 0:
        text += f"\n⏰ <b>{datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M')}</b>"
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🟢 تعطيل" if active else "🔴 تفعيل",
                callback_data="maint_toggle"
            )],
            [InlineKeyboardButton("✏️ الرسالة", callback_data="maint_edit")],
            [InlineKeyboardButton("⏰ وقت", callback_data="maint_time")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")],
        ]),
        parse_mode=ParseMode.HTML,
    )


async def cb_maint_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    m = db.get_maintenance()
    new = not m.get("active", False)
    db.set_maintenance(active=new)
    await q.answer(f"{'🔴 مفعّلة' if new else '🟢 معطّلة'}", show_alert=True)
    await cb_adm_maint(update, context)


async def cb_maint_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "✏️ أرسل رسالة الصيانة:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return MAINT_MSG


async def maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    db.set_maintenance(message=msg)
    await update.message.reply_text(
        f"✅ تم\n\n<code>{esc(msg)}</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔧", callback_data="adm_maint")]]),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def cb_maint_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "⏰ أرسل المدة بالدقائق (0 = إلغاء)",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return MAINT_TIME


async def maint_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        m = int(update.message.text.strip())
        if m < 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb()); return MAINT_TIME
    end = 0
    if m > 0:
        end = int(datetime.now().timestamp()) + m * 60
    db.set_maintenance(end_time=end)
    if end > 0:
        txt = f"✅ ستنتهي في {datetime.fromtimestamp(end).strftime('%H:%M')}"
    else:
        txt = "✅ تم الإلغاء"
    await update.message.reply_text(txt,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔧", callback_data="adm_maint")]]))
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Settings
# ═══════════════════════════════════════════════════════════
async def cb_adm_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    cfg = s()
    proofs = cfg.get("proofs_channel", "") or "❌ غير محددة"
    text = (
        f"🎨 <b>الإعدادات</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 هدية: <b>{fmt(cfg.get('daily_gift_points',0))}</b>\n"
        f"👥 إحالة: <b>{fmt(cfg.get('referral_points',0))}</b>\n"
        f"📞 الدعم: {cfg.get('support_channel','—')}\n"
        f"📢 الإثباتات: <code>{esc(str(proofs))}</code>\n\n"
        f"💬 الترحيب:\n<code>{esc(cfg.get('welcome',''))[:60]}</code>"
    )
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎁 هدية ({cfg.get('daily_gift_points',0)})", callback_data="set_gift"),
             InlineKeyboardButton(f"👥 إحالة ({cfg.get('referral_points',0)})", callback_data="set_ref")],
            [InlineKeyboardButton("💬 الترحيب", callback_data="set_welcome")],
            [InlineKeyboardButton("📞 الدعم", callback_data="set_channel")],
            [InlineKeyboardButton("📢 قناة الإثباتات", callback_data="set_proofs")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")],
        ]),
        parse_mode=ParseMode.HTML,
    )


async def cb_set_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    field = q.data.replace("set_", "")
    context.user_data["set_field"] = field
    hints = {
        "welcome": "💬 أرسل رسالة الترحيب",
        "gift": "🎁 أرسل عدد نقاط الهدية (رقم)",
        "ref": "👥 أرسل عدد نقاط الإحالة (رقم)",
        "channel": "📞 أرسل رابط الدعم",
        "proofs": (
            "📢 <b>قناة الإثباتات</b>\n\n"
            "أرسل:\n"
            "• <code>@my_channel</code>\n"
            "• أو <code>-1001234567890</code>\n"
            "• أو <code>-</code> لحذفها\n\n"
            "⚠️ البوت يجب أن يكون مشرفاً!"
        ),
    }
    await q.edit_message_text(
        f"{hints.get(field)}:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_only_kb(),
    )
    return SET_VALUE


async def set_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()
    field = context.user_data.get("set_field")
    if not field: return ConversationHandler.END
    km = {"welcome": "welcome", "gift": "daily_gift_points",
          "ref": "referral_points", "channel": "support_channel",
          "proofs": "proofs_channel"}
    k = km.get(field)
    if field in ("gift", "ref"):
        try:
            v = int(v)
            if v < 0: raise ValueError
        except Exception:
            await update.message.reply_text("❌ رقم غير صحيح", reply_markup=cancel_only_kb())
            return SET_VALUE
    if field == "proofs":
        if v == "-":
            db.update_settings({k: ""})
            await update.message.reply_text(
                "✅ تم حذف قناة الإثباتات",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 الإعدادات", callback_data="adm_set")]]),
            )
            return ConversationHandler.END
        try:
            test_msg = await context.bot.send_message(
                chat_id=v,
                text=("🧪 <b>اختبار قناة الإثباتات</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      "✅ البوت متصل ويعمل بنجاح!"),
                parse_mode=ParseMode.HTML,
            )
            await asyncio.sleep(3)
            try:
                await context.bot.delete_message(v, test_msg.message_id)
            except Exception:
                pass
            db.update_settings({k: v})
            await update.message.reply_text(
                f"✅ <b>تم تفعيل القناة!</b>\n\n📢 <code>{esc(v)}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 الإعدادات", callback_data="adm_set")]]),
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>فشل الاتصال!</b>\n\n<code>{esc(str(e))}</code>\n\n"
                f"تأكد من:\n• البوت مشرف\n• صلاحية النشر مفعّلة\n• المعرّف صحيح",
                parse_mode=ParseMode.HTML,
            )
            return SET_VALUE
        return ConversationHandler.END
    db.update_settings({k: v})
    await update.message.reply_text(
        "✅ تم",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 الإعدادات", callback_data="adm_set")]]),
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#   Backup / Cancel
# ═══════════════════════════════════════════════════════════
async def cb_adm_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    path = db.backup()
    if path:
        await q.edit_message_text(
            f"✅ <b>تم النسخ</b>\n📁 <code>{path}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")]]),
            parse_mode=ParseMode.HTML,
        )
    else:
        await q.edit_message_text("❌ فشل")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء")
    return ConversationHandler.END


async def error_handler(update, context):
    logger.error("Exception:", exc_info=context.error)


# ═══════════════════════════════════════════════════════════
#   Main
# ═══════════════════════════════════════════════════════════
def main():
    logger.info("🛒 Starting ASROM SHOP...")
    db.load()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start), group=0)
    app.add_handler(CommandHandler("admin", cmd_admin), group=0)
    app.add_handler(CommandHandler("cancel", cmd_cancel), group=0)

    app.add_handler(CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_global, pattern="^(back_main|admin_panel|noop)$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"), group=0)

    app.add_handler(CallbackQueryHandler(cb_balance, pattern="^balance$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_shop, pattern="^shop$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_view_product, pattern="^view_"), group=0)
    app.add_handler(CallbackQueryHandler(cb_buy, pattern="^buy_"), group=0)
    app.add_handler(CallbackQueryHandler(cb_daily, pattern="^daily$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_referral, pattern="^referral$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_purchases, pattern="^purchases$"), group=0)

    app.add_handler(CallbackQueryHandler(cb_adm_stats, pattern="^adm_stats$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_products, pattern="^adm_products$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_users, pattern="^adm_users$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_maint, pattern="^adm_maint$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_set, pattern="^adm_set$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_backup, pattern="^adm_backup$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_adm_channels, pattern="^adm_channels$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_del_channel, pattern="^delch_"), group=0)
    app.add_handler(CallbackQueryHandler(cb_toggle_product, pattern="^togglep_"), group=0)
    app.add_handler(CallbackQueryHandler(cb_delete_product, pattern="^delp_"), group=0)
    app.add_handler(CallbackQueryHandler(cb_maint_toggle, pattern="^maint_toggle$"), group=0)

    app.add_handler(CallbackQueryHandler(cb_adm_pl, pattern="^adm_pl$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_pl_list, pattern="^pl_list$"), group=0)
    app.add_handler(CallbackQueryHandler(cb_pl_delete, pattern="^pl_del_"), group=0)

    add_p_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_p_start, pattern="^adm_add_p$")],
        states={
            P_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, p_name)],
            P_EMOJI: [MessageHandler(filters.TEXT & ~filters.COMMAND, p_emoji)],
            P_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, p_desc)],
            P_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, p_price)],
            P_MODE: [CallbackQueryHandler(p_mode, pattern="^pmode_")],
            P_FIRST_CONTENT: [
                CallbackQueryHandler(p_first_content, pattern="^(pct_|mct_)"),
                MessageHandler(
                    filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                    p_first_content
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    add_c_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_add_content_start, pattern="^addc_")],
        states={
            AC_CONTENT: [
                CallbackQueryHandler(ac_content, pattern="^ctext_"),
                MessageHandler(
                    filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                    ac_content
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    edit_p_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_edit_product, pattern="^editp_"),
            CallbackQueryHandler(cb_manage_content, pattern="^mngc_"),
        ],
        states={
            PE_VALUE: [
                CallbackQueryHandler(cb_edit_field, pattern="^epf_"),
                CallbackQueryHandler(cb_manage_content, pattern="^mngc_"),
                CallbackQueryHandler(cb_del_content, pattern="^delc_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, pe_value),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    give_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_give_start, pattern="^adm_give$")],
        states={
            UP_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, up_user)],
            UP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, up_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_ban_start, pattern="^adm_ban$")],
        states={
            UB_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_user)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    msg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_msg_start, pattern="^adm_msg$")],
        states={
            MSG_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_user)],
            MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_text)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    bc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_bc_start, pattern="^adm_bc$")],
        states={
            BC_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bc_text)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    maint_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_maint_edit, pattern="^maint_edit$"),
            CallbackQueryHandler(cb_maint_time, pattern="^maint_time$"),
        ],
        states={
            MAINT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, maint_msg)],
            MAINT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, maint_time)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    set_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_set_field, pattern="^set_(welcome|gift|ref|channel|proofs)$"),
        ],
        states={
            SET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_value)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    add_ch_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_ch_start, pattern="^add_ch$")],
        states={
            ADD_CH_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_ch_id)],
            ADD_CH_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_ch_title)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    pl_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_pl_create_start, pattern="^pl_create$")],
        states={
            PL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_amount)],
            PL_MAX_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_max_uses)],
            PL_EXPIRE_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_expire_hours)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cancel_conv, pattern="^cancel_conv$"),
        ],
        per_message=False,
    )

    app.add_handler(add_p_conv, group=1)
    app.add_handler(add_c_conv, group=1)
    app.add_handler(edit_p_conv, group=1)
    app.add_handler(give_conv, group=1)
    app.add_handler(ban_conv, group=1)
    app.add_handler(msg_conv, group=1)
    app.add_handler(bc_conv, group=1)
    app.add_handler(maint_conv, group=1)
    app.add_handler(set_conv, group=1)
    app.add_handler(add_ch_conv, group=1)
    app.add_handler(pl_conv, group=1)

    app.add_error_handler(error_handler)

    logger.info("✅ Bot is ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()