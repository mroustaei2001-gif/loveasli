import shutil
import os, re, random, asyncio, logging, sqlite3, subprocess
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from html import escape as html_escape
import aiosqlite
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from telethon import TelegramClient
from telethon import utils
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 34162330
API_HASH = '3bb051fd52ebd9b40999d16070589fc2'
BOT_TOKEN = '8822939635:AAFL0R9R-OolOdMNy_H1uAWY2JcxIKtiuS8'
ADMINS = [8810172664, 6282695098]
MEDIA_DIR = 'media'
os.makedirs(MEDIA_DIR, exist_ok=True)
PROXY_LINKS_FILE = '/root/mtg_links.txt'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# Ensure premium session is accessible
if os.path.exists('/root/premium_session.session') and not os.path.exists('premium_session.session'):
    shutil.copy('/root/premium_session.session', 'premium_session.session')
if os.path.exists('/root/premium_session.session-journal') and not os.path.exists('premium_session.session-journal'):
    shutil.copy('/root/premium_session.session-journal', 'premium_session.session-journal')


# اضافه کردن ستون واترمارک به دیتابیس
try:
    import sqlite3 as _sqlite3
    _conn = _sqlite3.connect('auto_pub.db')
    _conn.execute("ALTER TABLE batch_posts ADD COLUMN has_watermark INTEGER DEFAULT 0")
    _conn.commit()
    _conn.close()
    print("✅ ستون has_watermark به دیتابیس اضافه شد")
except Exception as _e:
    if "duplicate column" not in str(_e).lower():
        print(f"️ خطا در اضافه کردن ستون: {_e}")

telethon_client = TelegramClient('reader_session', API_ID, API_HASH)
premium_client = TelegramClient('premium_session', API_ID, API_HASH)
PUBLISH_ERR = None
PREMIUM_ERR = None
DBG = ''
DBG_LIST = []

class DB:
    def __init__(self, path='auto_pub.db'):
        self.path = path
    async def init(self):
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT)")
            await conn.execute("CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, username TEXT UNIQUE)")
            await conn.execute("CREATE TABLE IF NOT EXISTS batches (id INTEGER PRIMARY KEY, admin_id INTEGER, created_at TEXT)")
            await conn.execute("CREATE TABLE IF NOT EXISTS batch_posts (id INTEGER PRIMARY KEY, batch_id INTEGER, source TEXT, msg_id INTEGER, text TEXT, media INTEGER, status TEXT DEFAULT 'pending', fmt TEXT, foot TEXT)")
            await conn.execute("CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY, post_id INTEGER, scheduled_at TEXT, target_chat INTEGER)")
            await conn.execute("CREATE TABLE IF NOT EXISTS published (id INTEGER PRIMARY KEY, source TEXT, msg_id INTEGER, published_at TEXT, UNIQUE(source, msg_id))")
            async with conn.execute("PRAGMA table_info(batch_posts)") as cur:
                cols = [row[1] for row in await cur.fetchall()]
            if 'is_spoiler' not in cols:
                await conn.execute("ALTER TABLE batch_posts ADD COLUMN is_spoiler INTEGER DEFAULT 0")
            for k, v in [('min_interval','60'),('max_interval','120'),('batch_size','5'),('main_channel','-1004461131517'),('footer',''),('format','bold'),('emoji','1'),('emoji_tag',''),('cap_emoji','0'),('cap_emoji_tag',''),('id_emoji_tag',''), ('cap_emoji_count', '5'), ('pre_fixed', ''), ('pre_count', '3'), ('sp_pre', '❤️🩵🩷'), ('rand_footer', ''), ('proxy_enabled', '1'), ('proxy_text', 'پروکسیزمون'), ('proxy_last_gen', '0'), ('pre_tag', '')]:
                await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            await conn.commit()
    async def get(self, key):
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
            return row[0] if row else None
    async def set(self, key, value):
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            await conn.commit()

db = DB()

class States(StatesGroup):
    add_source = State()
    set_interval = State()
    set_batch_size = State()
    set_main_channel = State()
    set_footer = State()
    set_gfoot = State()
    set_pfoot = State()
    set_ptext = State()
    set_time_all = State()
    set_emoji_tag = State()
    set_cap_emoji = State()
    set_cap_emoji_add = State()
    set_id_emoji = State()
    set_cap_emoji_count = State()
    set_sp_id_emoji = State()
    set_pre_fixed = State()
    set_pre_count = State()
    set_pre_tag = State()
    set_private_src = State()
    set_sp_pre = State()
    set_rand_footer = State()
    set_proxy_text = State()
    set_prev_footer = State()
    set_prev_caption = State()

import re
import time
def get_emojis(text):
    tags = re.findall(r'<tg-emoji[^>]*>.*?</tg-emoji>', text)
    if tags: return tags
    CHAR = "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\u2640-\u2642\u231a\u231b\u23cf\u23e9-\u23f3\u2b50\u2b55]"
    pat = re.compile(CHAR + "(?:[\ufe0f\U0001F3FB-\U0001F3FF]|\u200d" + CHAR + ")*[\ufe0f]?", re.UNICODE)
    return pat.findall(text)

def clean_text(text):
    if not text: return ''
    text = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#\w+', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def format_text(text, mode):
    parts = re.split(r'(<tg-emoji[^>]*>.*?</tg-emoji>)', text or '')
    t = ''.join(p if p.startswith('<tg-emoji') else html_escape(p) for p in parts)
    if mode == 'bold': return f"<b>{t}</b>"
    if mode == 'blockquote': return f"<blockquote>{t}</blockquote>"
    if mode == 'bold_blockquote': return f"<blockquote><b>{t}</b></blockquote>"
    return t

def extract_tags(message):
    if not message.entities: return (message.text or '').strip()
    tags = [e for e in message.entities if e.type == 'custom_emoji' and e.custom_emoji_id]
    if not tags: return (message.text or '').strip()
    u = (message.text or '').encode('utf-16-le')
    res, last = [], 0
    for e in tags:
        res.append(u[last*2:e.offset*2].decode('utf-16-le', 'ignore'))
        ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le', 'ignore') or '⭐'
        res.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
        last = e.offset + e.length
    res.append(u[last*2:].decode('utf-16-le', 'ignore'))
    return ''.join(res).strip()

def truncate_html(s, limit):
    if len(s) <= limit: return s
    cut = s[:limit]
    lt = cut.rfind('<'); gt = cut.rfind('>')
    if lt > gt: cut = cut[:lt]
    opens = re.findall(r'<(b|blockquote)>', cut)
    close = ''.join(f'</{t}>' for t in reversed(opens))
    return cut.rstrip() + '…' + close

def is_admin(uid): return uid in ADMINS

def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")]])

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 دسته جدید", callback_data="new_batch")],
        [InlineKeyboardButton(text="🚀 نهایی‌سازی و انتشار تاییدشده‌ها", callback_data="finalize")],
        [InlineKeyboardButton(text="👁️ لیست تایید شده‌ها", callback_data="approved_list")],
        [InlineKeyboardButton(text="📅 زمان‌بندی‌ها", callback_data="schedules")],
        [InlineKeyboardButton(text="➕ افزودن منابع", callback_data="add_source")],
        [InlineKeyboardButton(text="📋 لیست منابع", callback_data="list_sources")],
        [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="settings")],
        [InlineKeyboardButton(text="📊 آمار", callback_data="stats")],
    ])

async def show_menu(chat_id, text="🤖 ربات انتشار خودکار"):
    await bot.send_message(chat_id, text, reply_markup=main_menu_kb())

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("دسترسی غیرمجاز.")
    await show_menu(message.chat.id)

@router.callback_query(F.data == "menu")
async def cb_menu(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text("🤖 ربات انتشار خودکار", reply_markup=main_menu_kb())
    except Exception:
        try: await callback.message.delete()
        except Exception: pass
        await show_menu(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "stats")
async def cb_stats(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        src = (await (await conn.execute("SELECT COUNT(*) FROM sources")).fetchone())[0]
        pub = (await (await conn.execute("SELECT COUNT(*) FROM published")).fetchone())[0]
        sch = (await (await conn.execute("SELECT COUNT(*) FROM schedules")).fetchone())[0]
        app = (await (await conn.execute("SELECT COUNT(*) FROM batch_posts WHERE status='approved'")).fetchone())[0]
    await bot.send_message(callback.from_user.id, f"📊 آمار:\nمنابع: {src}\nمنتشر شده: {pub}\nتایید شده در انتظار: {app}\nزمان‌بندی شده: {sch}", reply_markup=menu_kb())
    await callback.answer()

@router.callback_query(F.data == "add_source")
async def cb_add_source(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "نام‌های کاربری منابع را بفرست:", reply_markup=menu_kb())
    await state.set_state(States.add_source)
    await callback.answer()

@router.message(States.add_source)
async def msg_add_source(message: types.Message, state: FSMContext):
    items = message.text.replace(',', ' ').split()
    added, dup = 0, 0
    async with aiosqlite.connect('auto_pub.db') as conn:
        for s in items:
            s = s.strip()
            if s.startswith('http'): s = s.split('/')[-1]
            s = s.lstrip('@').strip('/').rstrip('.')
            if not s: continue
            try:
                await conn.execute("INSERT INTO sources (username) VALUES (?)", (s,))
                added += 1
            except sqlite3.IntegrityError:
                dup += 1
        await conn.commit()
    await message.answer(f"✅ {added} منبع اضافه شد | {dup} تکراری.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "list_sources")
async def cb_list_sources(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        rows = await (await conn.execute("SELECT id, username FROM sources")).fetchall()
    if not rows:
        await bot.send_message(callback.from_user.id, "⚠️ منبعی ثبت نشده.", reply_markup=menu_kb())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"❌ {r[1]}", callback_data=f"del_src_{r[0]}")] for r in rows])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")])
        await bot.send_message(callback.from_user.id, "📋 منابع:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("del_src_"))
async def cb_del_src(callback: types.CallbackQuery):
    sid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("DELETE FROM sources WHERE id=?", (sid,))
        await conn.commit()
    await callback.answer("✅ حذف شد.")

def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱️ بازه", callback_data="set_interval"), InlineKeyboardButton(text="📢 کانال", callback_data="set_main_channel")],
        [InlineKeyboardButton(text="📝 فوتر", callback_data="set_footer"), InlineKeyboardButton(text="🎨 فرمت", callback_data="set_format")],
        [InlineKeyboardButton(text="✨ ایموجی کپشن", callback_data="set_cap_emoji"), InlineKeyboardButton(text="✨ روشن/خاموش", callback_data="toggle_cap_emoji")],
        [InlineKeyboardButton(text="🔢 تعداد ایموجی کپشن", callback_data="set_cap_emoji_count")],
        [InlineKeyboardButton(text="🎯 ایموجی ثابت اول کپشن", callback_data="set_pre_fixed")],
        [InlineKeyboardButton(text="🔢 تعداد ایموجی اول کپشن", callback_data="set_pre_count"), InlineKeyboardButton(text="⚠️ قلب اول کپشن اسپویلر", callback_data="set_sp_pre")],
        [InlineKeyboardButton(text="🎲 استخر ایموجی رندوم اول", callback_data="set_pre_tag")],
        [InlineKeyboardButton(text="🎲 فوتر رندوم", callback_data="set_rand_footer")],
        [InlineKeyboardButton(text="🆔 ایموجی ایدی", callback_data="set_id_emoji")],
        [InlineKeyboardButton(text="⚠️ ایموجی ایدی اسپویلر", callback_data="set_sp_id_emoji")],
        [InlineKeyboardButton(text="🔗 فوتر پروکسی", callback_data="set_proxy_footer")],
        [InlineKeyboardButton(text="💧 واترمارک", callback_data="set_watermark_id")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")],
    ])

async def send_settings(callback):
    vals = {}
    for k in ['min_interval','max_interval','main_channel','footer','format','cap_emoji','proxy_enabled','proxy_text','pre_fixed','pre_count']:
        vals[k] = await db.get(k)
    proxy_status = '✅ روشن' if vals['proxy_enabled'] == '1' else '❌ خاموش'
    text = f"⚙️ تنظیمات:\nبازه: {vals['min_interval']}-{vals['max_interval']} دقیقه\nکانال: {vals['main_channel']}\nفرمت: {vals['format']}\nفوتر: {vals['footer'] or '(خالی)'}\n✨ ایموجی کپشن: {'✅' if vals['cap_emoji']=='1' else '❌'}\n🎯 ثابت اول: {vals['pre_fixed'] or '(خالی)'} | رندوم: {vals['pre_count']}\n🔗 فوتر پروکسی: {proxy_status}\n   متن: {vals['proxy_text']}"
    try:
        await callback.message.edit_text(text, reply_markup=settings_kb())
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=settings_kb())

@router.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    await send_settings(callback)
    await callback.answer()

@router.callback_query(F.data == "set_proxy_footer")
async def cb_set_proxy_footer(callback: types.CallbackQuery):
    cur = await db.get('proxy_enabled')
    new_val = '0' if cur == '1' else '1'
    await db.set('proxy_enabled', new_val)
    await callback.answer(f"{'✅ روشن شد' if new_val == '1' else '❌ خاموش شد'}")
    await send_settings(callback)

@router.callback_query(F.data == "set_proxy_text")
async def cb_set_proxy_text(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "متن کلمه پروکسی را بفرست (مثلا: پروکسیزمون):")
    await state.set_state(States.set_proxy_text)
    await callback.answer()

@router.message(States.set_proxy_text)
async def msg_set_proxy_text(message: types.Message, state: FSMContext):
    await db.set('proxy_text', message.text.strip())
    await message.answer(f"✅ متن پروکسی ذخیره شد: {message.text.strip()}", reply_markup=menu_kb())
    await state.clear()

def get_proxy_links():
    try:
        with open(PROXY_LINKS_FILE, 'r') as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

def get_proxy_link():
    links = get_proxy_links()
    if not links:
        return None
    return random.choice(links)

def make_proxy_link(text):
    links = get_proxy_links()
    if not links:
        return text
    link = random.choice(links)
    return f'<a href="{link}">{text}</a>'

async def proxy_scheduler():
    while True:
        try:
            last_gen = await db.get('proxy_last_gen')
            now = datetime.now().timestamp()
            hours_7 = 7 * 60 * 60
            if not last_gen or float(last_gen) == 0 or (now - float(last_gen)) > hours_7:
                logger.info("🔄 ساخت پروکسی جدید...")
                try:
                    result = subprocess.run(['/root/make_users.sh', '20'], capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        await db.set('proxy_last_gen', str(now))
                        logger.info("✅ 20 پروکسی ساخته شد")
                    else:
                        logger.error(f"خطا در ساخت پروکسی: {result.stderr}")
                except Exception as e:
                    logger.error(f"خطا: {e}")
        except Exception as e:
            logger.error(f"proxy scheduler error: {e}")
        await asyncio.sleep(60)

@router.callback_query(F.data == "set_interval")
async def cb_set_interval(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "بازه به دقیقه: min max")
    await state.set_state(States.set_interval)
    await callback.answer()

@router.message(States.set_interval)
async def msg_set_interval(message: types.Message, state: FSMContext):
    try:
        a, b = map(int, message.text.split())
        await db.set('min_interval', a); await db.set('max_interval', b)
        await message.answer("✅ ذخیره شد.", reply_markup=menu_kb())
    except Exception:
        await message.answer("❌ فرمت اشتباه.")
    await state.clear()

@router.callback_query(F.data == "set_batch_size")
async def cb_set_batch_size(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "تعداد پست هر دسته:")
    await state.set_state(States.set_batch_size)
    await callback.answer()

@router.message(States.set_batch_size)
async def msg_set_batch_size(message: types.Message, state: FSMContext):
    try:
        await db.set('batch_size', int(message.text))
        await message.answer("✅ ذخیره شد.", reply_markup=menu_kb())
    except Exception:
        await message.answer("❌ عدد نامعتبر.")
    await state.clear()

@router.callback_query(F.data == "set_main_channel")
async def cb_set_main_channel(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "آیدی کانال اصلی:")
    await state.set_state(States.set_main_channel)
    await callback.answer()

@router.message(States.set_main_channel)
async def msg_set_main_channel(message: types.Message, state: FSMContext):
    await db.set('main_channel', message.text.strip())
    await message.answer("✅ ذخیره شد.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "set_footer")
async def cb_set_footer(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "متن فوتر پیش‌فرض (اختیاری):")
    await state.set_state(States.set_footer)
    await callback.answer()

@router.message(States.set_footer)
async def msg_set_footer(message: types.Message, state: FSMContext):
    await db.set('footer', extract_tags(message))
    await message.answer("✅ ذخیره شد.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "set_format")
async def cb_set_format(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bold", callback_data="fmt_bold")],
        [InlineKeyboardButton(text="Bold+Blockquote", callback_data="fmt_bold_blockquote")],
        [InlineKeyboardButton(text="Blockquote", callback_data="fmt_blockquote")],
        [InlineKeyboardButton(text="ساده", callback_data="fmt_plain")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")],
    ])
    await bot.send_message(callback.from_user.id, "فرمت پیش‌فرض:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("fmt_"))
async def cb_fmt(callback: types.CallbackQuery):
    await db.set('format', callback.data[4:])
    await callback.answer("✅ ذخیره شد.")

@router.callback_query(F.data == "toggle_emoji")
async def cb_emoji(callback: types.CallbackQuery):
    cur = await db.get('emoji')
    await db.set('emoji', '0' if cur == '1' else '1')
    await callback.answer("✅ تغییر کرد.")
    await send_settings(callback)

@router.callback_query(F.data == "toggle_cap_emoji")
async def cb_toggle_cap_emoji(callback: types.CallbackQuery):
    cur = await db.get('cap_emoji')
    await db.set('cap_emoji', '0' if cur == '1' else '1')
    await callback.answer("✅ تغییر کرد.")
    await send_settings(callback)

async def show_emoji_view(chat_id):
    tag = (await db.get('emoji_tag')) or ''
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش", callback_data="edit_emoji_tag"), InlineKeyboardButton(text="🗑 حذف", callback_data="del_emoji_tag")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")],
    ])
    await bot.send_message(chat_id, f"ایموجی‌های فعلی:\n{tag or '(خالی)'}", reply_markup=kb)

@router.callback_query(F.data == "set_emoji_tag")
async def cb_set_emoji_tag(callback: types.CallbackQuery):
    await show_emoji_view(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "edit_emoji_tag")
async def cb_edit_emoji_tag(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, 'خود ایموجی(های) پریمیوم را بفرست (از بخش پریمیوم کیبورد ایموجی) — آیدی خودکار استخراج می‌شود:')
    await state.set_state(States.set_emoji_tag)
    await callback.answer()

@router.callback_query(F.data == "del_emoji_tag")
async def cb_del_emoji_tag(callback: types.CallbackQuery):
    await db.set('emoji_tag', '')
    await callback.answer("✅ حذف شد.")
    await show_emoji_view(callback.from_user.id)

async def show_cap_view(chat_id):
    tag = (await db.get('cap_emoji_tag')) or ''
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن", callback_data="add_cap_emoji"), InlineKeyboardButton(text="✏️ ویرایش", callback_data="edit_cap_emoji")],
        [InlineKeyboardButton(text="🗑 حذف", callback_data="del_cap_emoji"), InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")],
    ])
    cnt = len([t for t in tag.split('|||||') if t.strip()])
    disp = tag if len(tag) <= 800 else tag[:800] + '…'
    await bot.send_message(chat_id, f"🔢 تعداد استخر: {cnt}\nایموجی‌های فعلی:\n{disp or '(خالی)'}", reply_markup=kb)

@router.callback_query(F.data == "set_cap_emoji")
async def cb_set_cap_emoji(callback: types.CallbackQuery):
    await show_cap_view(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "edit_cap_emoji")
async def cb_edit_cap_emoji(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "ایموجی‌های پریمیوم کپشن را بفرست:")
    await state.set_state(States.set_cap_emoji)
    await callback.answer()

@router.callback_query(F.data == "del_cap_emoji")
async def cb_del_cap_emoji(callback: types.CallbackQuery):
    await db.set('cap_emoji_tag', '')
    await callback.answer("✅ حذف شد.")
    await show_cap_view(callback.from_user.id)

@router.message(States.set_cap_emoji)
async def msg_set_cap_emoji(message: types.Message, state: FSMContext):
    tags = []
    if message.entities:
        u = (message.text or '').encode('utf-16-le')
        for e in message.entities:
            if e.type == 'custom_emoji' and e.custom_emoji_id:
                try:
                    ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le', 'ignore') or '⭐'
                except Exception:
                    ch = '⭐'
                tags.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
    if not tags and message.text:
        tags = get_emojis(message.text)
        if not tags: tags = [message.text.strip()]
    tag = "|||||".join(tags) if tags else message.text.strip()
    await db.set('cap_emoji_tag', tag)
    await db.set('cap_emoji', '1')
    await message.answer(f"✅ ذخیره و فعال شد:\n{tag}", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "add_cap_emoji")
async def cb_add_cap_emoji(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "ایموجی‌های جدید (پریمیوم/ساده) را بفرست — به استخر اضافه می‌شود (حداکثر 200):")
    await state.set_state(States.set_cap_emoji_add)
    await callback.answer()

@router.message(States.set_cap_emoji_add)
async def msg_add_cap_emoji(message: types.Message, state: FSMContext):
    tags = []
    if message.entities:
        u = (message.text or '').encode('utf-16-le')
        for e in message.entities:
            if e.type == 'custom_emoji' and e.custom_emoji_id:
                try: ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le','ignore') or '⭐'
                except Exception: ch = '⭐'
                tags.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
    if not tags and message.text:
        tags = get_emojis(message.text)
        if not tags: tags = [t for t in message.text.strip().split() if t]
    oldp = (await db.get('cap_emoji_tag')) or ''
    pool = [x for x in oldp.split('|||||') if x.strip()]
    pool += tags
    pool = pool[:200]
    await db.set('cap_emoji_tag', '|||||'.join(pool))
    await db.set('cap_emoji', '1')
    await message.answer(f"✅ {len(tags)} اضافه شد | مجموع استخر: {len(pool)}", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "set_pre_tag")
async def cb_set_pre_tag(callback: types.CallbackQuery, state: FSMContext):
    cur = (await db.get('pre_tag')) or ''
    cnt = len([t for t in cur.split('|||||') if t.strip()])
    await bot.send_message(callback.from_user.id, f"🎲 استخر ایموجی رندوم اول (فعلی: {cnt}) — ایموجی‌ها را بفرست (جایگزین می‌شود):")
    await state.set_state(States.set_pre_tag)
    await callback.answer()

@router.message(States.set_pre_tag)
async def msg_set_pre_tag(message: types.Message, state: FSMContext):
    tags = []
    if message.entities:
        u = (message.text or '').encode('utf-16-le')
        for e in message.entities:
            if e.type == 'custom_emoji' and e.custom_emoji_id:
                try: ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le','ignore') or '⭐'
                except Exception: ch = '⭐'
                tags.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
    if not tags and message.text:
        tags = get_emojis(message.text)
        if not tags: tags = [t for t in message.text.strip().split() if t]
    await db.set('pre_tag', '|||||'.join(tags[:200]))
    await message.answer(f"✅ استخر ایموجی رندوم اول: {len(tags[:200])}", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "set_private_src")
async def cb_set_private_src(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "🔐 لینک خصوصی کانال را بفرست (t.me/+...):\nربات عضو می‌شود و با آیدی عددی ذخیره می‌کند:")
    await state.set_state(States.set_private_src)
    await callback.answer()

@router.message(States.set_private_src)
async def msg_set_private_src(message: types.Message, state: FSMContext):
    from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
    link = (message.text or '').strip()
    hm = re.search(r'(?:\+|joinchat/)([A-Za-z0-9_\-]+)', link)
    if not hm:
        await message.answer("❌ لینک معتبر نیست. مثال: t.me/+ABC123")
        await state.clear(); return
    h = hm.group(1)
    cid = None
    err = ''
    try:
        if not telethon_client.is_connected(): await telethon_client.connect()
        up = await telethon_client(ImportChatInviteRequest(h))
        if up.chats: cid = utils.get_peer_id(up.chats[0])
    except Exception as e1:
        err = str(e1)
        logger.error(f"import invite: {e1}")
    if not cid:
        try:
            inv = await telethon_client(CheckChatInviteRequest(h))
            title = (getattr(inv,'title',None) or '').strip().lower()
            if title:
                async for d in telethon_client.iter_dialogs():
                    dt = (d.title or '').strip().lower()
                    if dt == title or title in dt or dt in title:
                        cid = d.id; break
        except Exception as e2:
            err += ' | ' + str(e2)
    # اگر هنوز پیدا نشد و قبلاً عضو بوده، لیست کانال‌های خصوصی را نشان بده
    if not cid and 'already a participant' in err:
        cands = []
        try:
            async for d in telethon_client.iter_dialogs():
                ent = getattr(d,'entity',None)
                if ent and getattr(ent,'username',None): continue
                if getattr(d,'is_channel',False) or getattr(d,'is_group',False):
                    cands.append((d.id, d.title or 'بدون نام'))
                if len(cands) >= 30: break
        except Exception as e3:
            logger.error(f"dialogs: {e3}")
        if cands:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"📺 {t[:30]}", callback_data=f"pickpriv_{i}")] for i,t in cands])
            await message.answer("ℹ️ اکانت قبلاً عضو است. کانال موردنظر را انتخاب کن:", reply_markup=kb)
            await state.clear(); return
    if cid:
        async with aiosqlite.connect('auto_pub.db') as conn:
            await conn.execute("INSERT INTO sources (username) VALUES (?)", (str(cid),))
            await conn.commit()
        await message.answer(f"✅ منبع خصوصی ذخیره شد (آیدی عددی: {cid}).", reply_markup=menu_kb())
    else:
        await message.answer(f"❌ خطا: {err[:300]}", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data.startswith("pickpriv_"))
async def cb_pickpriv(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("INSERT INTO sources (username) VALUES (?)", (str(cid),))
        await conn.commit()
    await callback.answer(f"✅ منبع خصوصی ذخیره شد: {cid}")

async def show_id_view(chat_id):
    tag = (await db.get('id_emoji_tag')) or ''
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش", callback_data="edit_id_emoji"), InlineKeyboardButton(text="🗑 حذف", callback_data="del_id_emoji")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")],
    ])
    await bot.send_message(chat_id, f"ایموجی ایدی فعلی:\n{tag or '(خالی)'}", reply_markup=kb)

@router.callback_query(F.data == "set_id_emoji")
async def cb_set_id_emoji(callback: types.CallbackQuery):
    await show_id_view(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "edit_id_emoji")
async def cb_edit_id_emoji(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "ایموجی پریمیوم برای خط ایدی کانال بفرست:")
    await state.set_state(States.set_id_emoji)
    await callback.answer()

@router.callback_query(F.data == "del_id_emoji")
async def cb_del_id_emoji(callback: types.CallbackQuery):
    await db.set('id_emoji_tag', '')
    await callback.answer("✅ حذف شد.")
    await show_id_view(callback.from_user.id)

@router.message(States.set_id_emoji)
async def msg_set_id_emoji(message: types.Message, state: FSMContext):
    tags = []
    if message.entities:
        u = (message.text or '').encode('utf-16-le')
        for e in message.entities:
            if e.type == 'custom_emoji' and e.custom_emoji_id:
                try:
                    ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le', 'ignore') or '⭐'
                except Exception:
                    ch = '⭐'
                tags.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
    tag = " ".join(tags) if tags else message.text.strip()
    await db.set('id_emoji_tag', tag)
    await message.answer(f"✅ ذخیره شد:\n{tag}", reply_markup=menu_kb())
    await state.clear()

@router.message(States.set_emoji_tag)
async def msg_set_emoji_tag(message: types.Message, state: FSMContext):
    tags = []
    if message.entities:
        u = (message.text or '').encode('utf-16-le')
        for e in message.entities:
            if e.type == 'custom_emoji' and e.custom_emoji_id:
                try:
                    ch = u[e.offset*2:(e.offset+e.length)*2].decode('utf-16-le', 'ignore') or '⭐'
                except Exception:
                    ch = '⭐'
                tags.append(f'<tg-emoji emoji-id="{e.custom_emoji_id}">{ch}</tg-emoji>')
    tag = " ".join(tags) if tags else message.text.strip()
    await db.set('emoji_tag', tag)
    await message.answer(f"✅ ذخیره شد:\n{tag}", reply_markup=menu_kb())
    await state.clear()

async def resolve_source(name):
    try:
        return await telethon_client.get_entity(name)
    except Exception:
        from telethon import functions
        try:
            r = await telethon_client(functions.messages.ImportChatInvite(hash=name.lstrip('+').strip()))
            if r.chats: return r.chats[0]
        except Exception:
            pass
        try:
            return await telethon_client.get_entity(int(name))
        except Exception:
            return None

async def get_album_paths(source, msg_id):
    try:
        if not telethon_client.is_connected(): await telethon_client.connect()
        entity = await telethon_client.get_entity(source)
        msg = await telethon_client.get_messages(entity, ids=msg_id)
        if not msg or not msg.grouped_id:
            p = await get_media_path(source, msg_id); return [p] if p else []
        ids = []
        async for m in telethon_client.iter_messages(entity, min_id=msg_id-10, max_id=msg_id+10):
            if m.grouped_id == msg.grouped_id and m.media: ids.append(m.id)
        ids.sort()
        paths = []
        for i in ids:
            base = os.path.join(MEDIA_DIR, f"{source.strip('@')}_{i}")
            found = None
            for ext in ('.jpg', '.mp4', '.gif', '.webm'):
                if os.path.exists(base+ext): found = base+ext; break
            if not found:
                mm = await telethon_client.get_messages(entity, ids=i)
                mime = (mm.file.mime_type or '').lower() if mm.file else ''
                if 'video/mp4' in mime or 'video/webm' in mime or 'gif' in mime:
                    ext = '.mp4'
                else:
                    ext = '.jpg'
                found = base+ext
                print(f"📥 دانلود آلبوم: {source}/{i} -> {found} (MIME: {mime})")
                await telethon_client.download_media(mm, found)
            if found and os.path.exists(found): paths.append(found)
        return paths or ([await get_media_path(source, msg_id)])
    except Exception as e:
        logger.error(f"album: {e}")
        p = await get_media_path(source, msg_id); return [p] if p else []

async def get_media_path(source, msg_id):
    base = os.path.join(MEDIA_DIR, f"{source.strip('@')}_{msg_id}")
    for ext in ('.jpg', '.mp4', '.gif', '.webm'):
        if os.path.exists(base+ext): return base+ext
    path = base + '.jpg'
    if not telethon_client.is_connected():
        await telethon_client.connect()
    try:
        entity = await telethon_client.get_entity(source)
        msg = await telethon_client.get_messages(entity, ids=msg_id)
        if msg and msg.media:
            mime = (msg.file.mime_type or '').lower() if msg.file else ''
            if 'video/mp4' in mime or 'video/webm' in mime or 'gif' in mime:
                ext = '.mp4'
            else:
                ext = '.jpg'
            path = base+ext
            print(f"📥 دانلود: {source}/{msg_id} -> {path} (MIME: {mime})")
            await telethon_client.download_media(msg, path)
            return path if os.path.exists(path) else None
    except Exception as e:
        logger.error(f"media dl: {e}")
    return None

@router.callback_query(F.data == "new_batch")
async def cb_new_batch(callback: types.CallbackQuery):
    chat_id=callback.from_user.id
    for (cid,mid) in list(PREVIEW_MSGS):
        if cid==chat_id:
            try: await bot.delete_message(chat_id, mid)
            except Exception: pass
            PREVIEW_MSGS.remove((cid,mid))
    status=await bot.send_message(chat_id, "⏳ در حال ساخت دسته... صبر کن")
    await callback.answer()
    await generate_batch(chat_id)
    try: await status.delete()
    except Exception: pass

async def generate_batch(chat_id):
    if not telethon_client.is_connected(): await telethon_client.connect()
    async with aiosqlite.connect('auto_pub.db') as conn:
        sources = await (await conn.execute("SELECT id, username FROM sources")).fetchall()
        used = set()
        for r in await (await conn.execute("SELECT source, msg_id FROM published")).fetchall(): used.add((r[0],r[1]))
        for r in await (await conn.execute("SELECT source, msg_id FROM batch_posts")).fetchall(): used.add((r[0],r[1]))
    if not sources:
        return await bot.send_message(chat_id, "⚠️ منبعی نیست.", reply_markup=menu_kb())
    GROUP_SIZE=5
    total_groups=(len(sources)+GROUP_SIZE-1)//GROUP_SIZE
    cur_idx_str=await db.get('batch_group_index')
    try: cur_idx=int(cur_idx_str) if cur_idx_str else 0
    except Exception: cur_idx=0
    cur_idx=cur_idx%total_groups
    excl=set(); main_id=None
    mc=((await db.get('main_channel')) or '').strip().lstrip('@')
    if mc: excl.add(mc.lower())
    try:
        me=await bot.get_me()
        if me.username: excl.add(me.username.lower())
    except Exception: pass
    try:
        chat=await bot.get_chat(((await db.get('main_channel')) or '').strip())
        if getattr(chat,'username',None): excl.add(chat.username.lower())
        main_id=chat.id
    except Exception:
        try:
            ment=await telethon_client.get_entity(((await db.get('main_channel')) or '').strip())
            main_id=utils.get_peer_id(ment)
            if getattr(ment,'username',None): excl.add(ment.username.lower())
        except Exception: pass

    srcs=sources[cur_idx*GROUP_SIZE:(cur_idx+1)*GROUP_SIZE]
    media_all=[]; text_all=[]; seen_grouped=set(); errs=[]
    deadline=time.monotonic()+10
    async with aiosqlite.connect('auto_pub.db') as conn:
        for sid,uname in srcs:
            if time.monotonic()>deadline: break
            uname=uname.strip()
            if uname.startswith('http'): uname=uname.split('/')[-1]
            uname=uname.lstrip('@').strip('/').rstrip('.')
            if uname.lower() in excl: continue
            try:
                try:
                    if uname.lstrip('-').isdigit():
                        entity=await telethon_client.get_entity(int(uname))
                    else:
                        entity=await resolve_source(uname)
                except Exception as e1:
                    try:
                        hm=re.search(r'(?:\+|joinchat/)([A-Za-z0-9_\-]+)',uname)
                        if hm:
                            from telethon.tl.functions.messages import ImportChatInviteRequest
                            up=await telethon_client(ImportChatInviteRequest(hm.group(1)))
                            if up.chats: entity=up.chats[0]
                            else: entity=None
                        else: entity=None
                    except Exception as e2:
                        entity=None
                if not entity:
                    errs.append(f"{uname}: resolve"); continue
                try: eid=int(uname) if uname.lstrip('-').isdigit() else utils.get_peer_id(entity)
                except Exception: eid=None
                if main_id and eid and eid==main_id: continue
                if str(uname).startswith('+'):
                    await conn.execute("UPDATE sources SET username=? WHERE id=?", (str(utils.get_peer_id(entity)), sid))
                async for m in telethon_client.iter_messages(entity, limit=200):
                    if time.monotonic()>deadline: break
                    if not m: continue
                    is_used=(uname,m.id) in used
                    if getattr(m,'sticker',None): continue
                    if isinstance(m.media,MessageMediaDocument) and m.file and ('webp' in (m.file.mime_type or '') or 'webm' in (m.file.mime_type or '')): continue
                    has_sp=bool(getattr(m,'media_spoiler',False)) or any(getattr(e,'type','')=='spoiler' for e in (m.entities or []))
                    _txt=m.text or ''
                    if re.search(r'https?://|t\.me/|www\.|telegram\.me', _txt, re.I): continue
                    if any(getattr(e,'type','') in ('url','text_link') for e in (m.entities or [])): continue
                    ct=clean_text(_txt)
                    ct=re.sub(r'@[A-Za-z0-9_]{4,}','',ct)
                    ct=re.sub(r'\s+',' ',ct).strip()
                    item=None
                    if m.grouped_id:
                        if m.grouped_id in seen_grouped: continue
                        seen_grouped.add(m.grouped_id)
                        if isinstance(m.media,(MessageMediaPhoto,MessageMediaDocument)):
                            item=(uname,m.id,ct,1 if has_sp else 0,'album',m.date)
                    elif isinstance(m.media,MessageMediaPhoto):
                        item=(uname,m.id,ct,1 if has_sp else 0,'photo',m.date)
                    elif isinstance(m.media,MessageMediaDocument) and m.file and m.file.mime_type=='video/mp4':
                        item=(uname,m.id,ct,1 if has_sp else 0,'gif',m.date)
                    elif not m.media and ct and len(ct)>=3:
                        item=(uname,m.id,ct,1 if has_sp else 0,'text',m.date)
                    if item:
                        if item[4]=='text': text_all.append((is_used,item))
                        else: media_all.append((is_used,item))
            except Exception as ex:
                errs.append(f"{uname}: {str(ex)[:40]}")
                logger.error(f"fetch {uname}: {ex}")
    # گروه‌بندی بر اساس منبع
    from_src = {}
    for is_used, item in media_all + text_all:
        if item[4] == 'text' and len(item[2] or '') < 3: continue
        uname = item[0]
        if uname not in from_src: from_src[uname] = []
        from_src[uname].append((is_used, item))
    chosen = []
    src_list = list(from_src.keys())
    random.shuffle(src_list)
    for uname in src_list:
        if len(chosen) >= 5: break
        items = sorted(from_src[uname], key=lambda x: x[0])
        chosen.append(items[0][1])
    if len(chosen) < 5:
        all_items = []
        for uname in from_src:
            for is_used, item in from_src[uname]:
                all_items.append((is_used, item))
        all_items.sort(key=lambda x: x[0])
        for is_used, item in all_items:
            if len(chosen) >= 5: break
            if item in chosen: continue
            chosen.append(item)
    await db.set('batch_group_index', str((cur_idx+1)%total_groups))
    if not chosen:
        msg=f"⚠️ پستی از دسته {cur_idx+1}/{total_groups} پیدا نشد."
        if errs: msg+="\n🔍 " + " | ".join(errs[:5])
        return await bot.send_message(chat_id, msg, reply_markup=menu_kb())
    random.shuffle(chosen)
    final=chosen[:5]
    async with aiosqlite.connect('auto_pub.db') as conn:
        cur=await conn.execute("INSERT INTO batches (admin_id, created_at) VALUES (?,?)",(chat_id,datetime.now().isoformat()))
        batch_id=cur.lastrowid
        ids=[]
        for uname,mid,txt,sp,kind,dt in final:
            cur2=await conn.execute("INSERT INTO batch_posts (batch_id,source,msg_id,text,media,is_spoiler) VALUES (?,?,?,?,?,?)",(batch_id,uname,mid,txt,(0 if kind=='text' else 1),sp))
            ids.append(cur2.lastrowid)
        await conn.commit()
    srcs_names=list(set(t[0] for t in final))
    await bot.send_message(chat_id, f"🎲 دسته {cur_idx+1}/{total_groups} - {len(ids)} پست از {len(srcs_names)} منبع:", reply_markup=menu_kb())
    for pid in ids: await send_preview(chat_id,pid)

PREVIEW_MSGS=[]
PREVIEW_PID={}
EDIT_MSG = {}
async def restore_preview(pid, is_sp):
    info = EDIT_MSG.pop(pid, None)
    if info:
        cid, mid = info
        try:
            await bot.edit_message_reply_markup(chat_id=cid, message_id=mid, reply_markup=preview_kb(pid, is_sp))
        except Exception:
            pass

async def cleanup_chat(chat_id):
    for (cid,mid) in list(PREVIEW_MSGS):
        if cid==chat_id:
            try: await bot.delete_message(chat_id, mid)
            except Exception: pass
            PREVIEW_MSGS.remove((cid,mid))
async def send_preview(chat_id, pid):
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT source, msg_id, text, media, is_spoiler, COALESCE(has_watermark, 0) as has_watermark FROM batch_posts WHERE id=?", (pid,))).fetchone()
    if not row: return
    source, mid, text, media, is_spoiler, has_watermark = row[0], row[1], row[2], row[3], row[4], (row[5] if len(row) > 5 else 0)
    kb = preview_kb(pid, is_spoiler, has_watermark)
    def reg(m):
        try:
            lst = m if isinstance(m,(list,tuple)) else [m]
            for x in lst:
                PREVIEW_MSGS.append((chat_id,x.message_id)); PREVIEW_PID.setdefault(pid,[]).append(x.message_id)
        except Exception: pass
    if media:
        paths = await get_album_paths(source, mid)
        if len(paths) > 1:
            from aiogram.types import InputMediaPhoto, InputMediaVideo
            ml=[]
            for i,p in enumerate(paths):
                ml.append(InputMediaPhoto(media=FSInputFile(p), has_spoiler=bool(is_spoiler), caption=(text or None if i==0 else None)))
            _m=await bot.send_media_group(chat_id, ml)
            reg(_m)
            _c=await bot.send_message(chat_id, "🎞 آلبوم بالا — تایید/رد:", reply_markup=kb)
            reg(_c)
            return
        path = paths[0] if paths else None
        if path:
            if path.endswith('.mp4'):
                _m=await bot.send_animation(chat_id, FSInputFile(path), caption=text or None, reply_markup=kb); reg(_m)
            else:
                _m=await bot.send_photo(chat_id, FSInputFile(path), caption=text or None, reply_markup=kb); reg(_m)
            return
    _m=await bot.send_message(chat_id, text or "(بدون متن)", reply_markup=kb); reg(_m)

async def after_review(chat_id, batch_id):
    async with aiosqlite.connect('auto_pub.db') as conn:
        left = (await (await conn.execute("SELECT COUNT(*) FROM batch_posts WHERE batch_id=? AND status='pending'", (batch_id,))).fetchone())[0]
    if left == 0:
        await show_finalize(chat_id)

@router.callback_query(F.data.startswith("approve_"))
async def cb_approve(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT batch_id FROM batch_posts WHERE id=?", (pid,))).fetchone()
        await conn.execute("UPDATE batch_posts SET status='approved' WHERE id=?", (pid,))
        await conn.commit()
    try: await callback.message.delete()
    except Exception: pass
    for _mid in PREVIEW_PID.pop(pid,[]):
        try: await bot.delete_message(callback.from_user.id, _mid)
        except Exception: pass
    await after_review(callback.from_user.id, row[0])
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def cb_reject(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT batch_id FROM batch_posts WHERE id=?", (pid,))).fetchone()
        await conn.execute("UPDATE batch_posts SET status='rejected' WHERE id=?", (pid,))
        await conn.commit()
    try: await callback.message.delete()
    except Exception: pass
    for _mid in PREVIEW_PID.pop(pid,[]):
        try: await bot.delete_message(callback.from_user.id, _mid)
        except Exception: pass
    await after_review(callback.from_user.id, row[0])
    await callback.answer()

async def show_finalize(chat_id):
    async with aiosqlite.connect('auto_pub.db') as conn:
        n = (await (await conn.execute("SELECT COUNT(*) FROM batch_posts WHERE status='approved'")).fetchone())[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 تغییر فونت کلی", callback_data="gfmt"), InlineKeyboardButton(text="📝 فوتر کلی", callback_data="gfoot")],
        [InlineKeyboardButton(text="✏️ ویرایش تکی پست‌ها", callback_data="edit_list")],
        [InlineKeyboardButton(text="🚀 انتشار پست‌های نهایی", callback_data="pub_final"), InlineKeyboardButton(text="📅 زمان‌بندی همه", callback_data="sched_all")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")],
    ])
    await bot.send_message(chat_id, f"✅ {n} پست تایید شده. تغییرات نهایی:", reply_markup=kb)

@router.callback_query(F.data == "finalize")
async def cb_finalize(callback: types.CallbackQuery):
    await show_finalize(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "gfmt")
async def cb_gfmt(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bold", callback_data="gfset_bold")],
        [InlineKeyboardButton(text="Bold+Blockquote", callback_data="gfset_bold_blockquote")],
        [InlineKeyboardButton(text="Blockquote", callback_data="gfset_blockquote")],
        [InlineKeyboardButton(text="ساده", callback_data="gfset_plain")],
        [InlineKeyboardButton(text="🔙", callback_data="finalize")],
    ])
    await bot.send_message(callback.from_user.id, "فونت کلی پست‌های تایید شده:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("gfset_"))
async def cb_gfset(callback: types.CallbackQuery):
    mode = callback.data.split("_", 1)[1]
    await db.set('format', mode)
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET fmt=? WHERE status='approved'", (mode,))
        await conn.commit()
    await callback.answer("✅ فونت کلی اعمال شد.")
    await show_finalize(callback.from_user.id)

@router.callback_query(F.data == "gfoot")
async def cb_gfoot(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "متن فوتر کلی را بفرست (می‌توانی ایموجی پریمیوم هم بگذاری):")
    await state.set_state(States.set_gfoot)
    await callback.answer()

@router.message(States.set_gfoot)
async def msg_gfoot(message: types.Message, state: FSMContext):
    t = extract_tags(message)
    await db.set('footer', t)
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET foot=? WHERE status='approved'", (t,))
        await conn.commit()
    await message.answer("✅ آیدی/فوتر کلی اعمال شد.", reply_markup=menu_kb())
    await show_finalize(message.chat.id)
    await state.clear()

@router.callback_query(F.data == "edit_list")
async def cb_edit_list(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        rows = await (await conn.execute("SELECT id, text FROM batch_posts WHERE status='approved' ORDER BY id")).fetchall()
    if not rows:
        await bot.send_message(callback.from_user.id, "⚠️ پست تایید شده‌ای نیست.", reply_markup=menu_kb())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✏️ #{r[0]} {(r[1] or '')[:25]}", callback_data=f"edit_{r[0]}")] for r in rows])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 نهایی‌سازی", callback_data="finalize")])
        await bot.send_message(callback.from_user.id, "✏️ پست را انتخاب کن:", reply_markup=kb)
    await callback.answer()

async def show_edit(chat_id, pid):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 فونت", callback_data=f"pfmt_{pid}"), InlineKeyboardButton(text="📝 فوتر", callback_data=f"pfoot_{pid}")],
        [InlineKeyboardButton(text="✏️ ویرایش متن", callback_data=f"ptext_{pid}")],
        [InlineKeyboardButton(text="🔙 نهایی‌سازی", callback_data="finalize")],
    ])
    await bot.send_message(chat_id, f"✏️ ویرایش پست #{pid}:", reply_markup=kb)

@router.callback_query(F.data.startswith("edit_"))
async def cb_edit(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT source, msg_id, text, media FROM batch_posts WHERE id=?", (pid,))).fetchone()
    if row:
        source, mid, text, media = row
        if media:
            path = await get_media_path(source, mid)
            if path:
                await bot.send_photo(callback.from_user.id, FSInputFile(path), caption=text or None)
            else:
                await bot.send_message(callback.from_user.id, text or "")
        else:
            await bot.send_message(callback.from_user.id, text or "")
    await show_edit(callback.from_user.id, pid)
    await callback.answer()

@router.callback_query(F.data.startswith("pfmt_"))
async def cb_pfmt(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bold", callback_data=f"pfset_{pid}_bold")],
        [InlineKeyboardButton(text="Bold+Blockquote", callback_data=f"pfset_{pid}_bold_blockquote")],
        [InlineKeyboardButton(text="Blockquote", callback_data=f"pfset_{pid}_blockquote")],
        [InlineKeyboardButton(text="ساده", callback_data=f"pfset_{pid}_plain")],
        [InlineKeyboardButton(text="🔙", callback_data=f"edit_{pid}")],
    ])
    await bot.send_message(callback.from_user.id, "فونت این پست:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("pfset_"))
async def cb_pfset(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    mode = callback.data.split("_", 2)[2]
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET fmt=? WHERE id=?", (mode, pid))
        await conn.commit()
    await callback.answer("✅ اعمال شد.")
    await show_edit(callback.from_user.id, pid)

@router.callback_query(F.data.startswith("pfoot_"))
async def cb_pfoot(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    await state.update_data(pid=pid)
    await bot.send_message(callback.from_user.id, "فوتر این پست را بفرست:")
    await state.set_state(States.set_pfoot)
    await callback.answer()

@router.message(States.set_pfoot)
async def msg_pfoot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get('pid')
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET foot=? WHERE id=?", (extract_tags(message), pid))
        await conn.commit()
    await message.answer("✅ اعمال شد.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data.startswith("ptext_"))
async def cb_ptext(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    await state.update_data(pid=pid)
    await bot.send_message(callback.from_user.id, "متن/کپشن جدید این پست را بفرست:")
    await state.set_state(States.set_ptext)
    await callback.answer()

@router.message(States.set_ptext)
async def msg_ptext(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get('pid')
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET text=? WHERE id=?", (extract_tags(message), pid))
        await conn.commit()
    await message.answer("✅ متن اعمال شد.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "pub_final")
async def cb_pub_final(callback: types.CallbackQuery):
    await callback.answer("در حال انتشار...")
    asyncio.create_task(publish_all_approved(callback.from_user.id))

async def publish_all_approved(chat_id):
    global PUBLISH_ERR, PREMIUM_ERR, DBG
    wait_msg = await bot.send_message(chat_id, "⏳ لطفاً صبر کنید تا پست‌ها ارسال شوند...")
    try:
        PREMIUM_ERR = None
        async with aiosqlite.connect('auto_pub.db') as conn:
            ids = [r[0] for r in await (await conn.execute("SELECT id FROM batch_posts WHERE status='approved' ORDER BY id")).fetchall()]
        n = 0
        for pid in ids:
            if await do_publish(pid): n += 1
            await asyncio.sleep(2)
        msg = f"✅ {n} از {len(ids)} پست نهایی منتشر شد."
        if n < len(ids): msg += f"\n❌ خطا: {PUBLISH_ERR or 'نامشخص'}"
        elif PREMIUM_ERR: msg += f"\n⚠️ اکانت پریمیوم نفرستاد ({PREMIUM_ERR[:150]}) — پست‌ها بدون ایموجی پریمیوم رفتند. اکانت پریمیوم را عضو کانال کن!"
        DBG_LIST.clear()
        msg += "\n🔍 " + " | ".join(DBG_LIST[-8:])
        try: await wait_msg.delete()
        except Exception: pass
        try: await status_msg.delete()
        except Exception: pass
        try:
            if status_msg: await status_msg.delete()
        except Exception: pass
        await cleanup_chat(chat_id)
        await show_menu(chat_id, msg + "\n\n🤖 ربات انتشار خودکار")
    except Exception as e:
        PUBLISH_ERR = str(e)
        logger.error(f"publish_all: {e}")
        await bot.send_message(chat_id, f"❌ خطا: {e}", reply_markup=menu_kb())


def apply_watermark_video(video_path, watermark_text):
    import subprocess
    try:
        base, ext = os.path.splitext(video_path)
        output_path = base + '_wm' + ext
        font = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        
        # استفاده از الحاق رشته‌ای ساده برای جلوگیری از خطای سینتکس
        vf = "drawtext=text='" + str(watermark_text) + "':fontfile=" + font + ":fontcolor=white:alpha=0.35:fontsize=h/20:x=(w-text_w)/2:y=(h-text_h)/2+(h/8)"
        
        ext_lower = ext.lower()
        if ext_lower in ['.gif', '.webm', '.mp4']:
            if ext_lower == '.gif':
                cmd = ['ffmpeg', '-y', '-i', video_path, '-vf', vf, '-loop', '0', output_path]
            else:
                cmd = ['ffmpeg', '-y', '-i', video_path, '-vf', vf, '-c:v', 'libx264', '-c:a', 'copy', '-preset', 'fast', output_path]
            
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode == 0 and os.path.exists(output_path):
                return output_path
            
            print('❌ ffmpeg failed on:', video_path)
            print('Command:', ' '.join(cmd))
            print('Full Stderr:\n', r.stderr)
        return video_path
    except Exception as e:
        print('⚠️ video watermark error:', e)
        return video_path

def apply_watermark(image_path, watermark_text):
    try:
        if image_path.endswith(('.mp4', '.gif', '.webm')):
            return apply_watermark_video(image_path, watermark_text)
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(image_path).convert("RGBA")
        txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)
        
        font_size = max(20, min(img.size[0] // 15, 60))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img.size[0] - text_width) // 2
        y = (img.size[1] - text_height) // 2 + (img.size[1] // 8)
        
        draw.text((x, y), watermark_text, fill=(255, 255, 255, 80), font=font)
        
        watermarked = Image.alpha_composite(img, txt_layer)
        
        output_path = image_path.rsplit('.', 1)[0] + '_wm.jpg'
        watermarked.convert("RGB").save(output_path, "JPEG", quality=95)
        return output_path
    except Exception as e:
        print(f"⚠️ خطا در اعمال واترمارک: {e}")
        return image_path

async def do_publish(pid):
    global PUBLISH_ERR, PREMIUM_ERR, DBG
    NL = chr(10)
    try:
        async with aiosqlite.connect('auto_pub.db') as conn:
            row = await (await conn.execute("SELECT source, msg_id, text, media, fmt, foot, is_spoiler, COALESCE(has_watermark, 0) as has_watermark FROM batch_posts WHERE id=?", (pid,))).fetchone()
        if not row:
            PUBLISH_ERR = "پست پیدا نشد"
            return False
        source, mid, text, media, pfmt, pfoot, is_spoiler = row[0], row[1], row[2], row[3], row[4], row[5], row[6]
        source, mid, text, media, pfmt, pfoot, is_spoiler = row[0], row[1], row[2], row[3], row[4], row[5], row[6]
        has_watermark = row[7] if len(row) > 7 else 0
        has_watermark = row[7] if len(row) > 7 else 0
        is_spoiler = bool(is_spoiler)
        fmt = pfmt or await db.get('format')
        extra = pfoot or ''
        rpool = [x.strip() for x in ((await db.get('rand_footer')) or '').split('|||||') if x.strip()]
        if rpool:
            base_footer = random.choice(rpool)
        else:
            base_footer = (await db.get('footer')) or ''
            if base_footer:
                fpool = [x.strip() for x in re.split(r'\|\|\|\|\||\n', base_footer) if x.strip()]
                if fpool: base_footer = random.choice(fpool)
        ch = (await db.get('main_channel')).strip()
        try: channel = int(ch)
        except ValueError: channel = ch
        def tlen(s): return len(s.encode('utf-16-le')) // 2
        def strip_prem(s):
            return re.sub(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', lambda mm: mm.group(1), s)
        def remove_emoji_tags(s):
            return re.sub(r'<tg-emoji[^>]*>[^<]*</tg-emoji>', '', s)
        body_full = format_text(text or '', fmt)
        cap_footer = ''
        if not is_spoiler and (await db.get('cap_emoji')) == '1':
            cap_raw = (await db.get('cap_emoji_tag')) or ''
            cap_em = get_emojis(cap_raw)
            pool = list(dict.fromkeys(cap_em))[:200] if cap_em else [t.strip() for t in cap_raw.split('|||||') if t.strip()][:200]
            if pool:
                try: ccount = int(await db.get('cap_emoji_count') or 5)
                except Exception: ccount = 5
                cap_footer = NL + NL + ''.join(random.sample(pool, min(ccount, len(pool))))
        if is_spoiler:
            pre = ((await db.get('sp_pre')) or '❤️🩵🩷') + ' '
        else:
            fixed = (await db.get('pre_fixed')) or ''
            pre_raw = (await db.get('pre_tag')) or ''
            pre_em = get_emojis(pre_raw)
            pool0 = list(dict.fromkeys(pre_em))[:200] if pre_em else [t.strip() for t in pre_raw.split('|||||') if t.strip()][:200]
            try: pcount = int(await db.get('pre_count') or 3)
            except Exception: pcount = 3
            rand0 = ''.join(random.sample(pool0, min(pcount, len(pool0)))) if pool0 else ''
            pre = (fixed + rand0 + " ") if (fixed or rand0) else ""
        ch_name = str(channel)
        try:
            chat = await bot.get_chat(channel)
            if getattr(chat, 'username', None): ch_name = '@' + chat.username
        except Exception:
            try:
                if not telethon_client.is_connected(): await telethon_client.connect()
                ent = await telethon_client.get_entity(channel)
                if getattr(ent, 'username', None): ch_name = '@' + ent.username
            except Exception:
                pass
        idtag = (await db.get('id_emoji_tag')) or ''
        id_em = get_emojis(idtag)
        em = random.choice(id_em) if id_em else ''
        em_used = ((await db.get('sp_id_emoji')) or '🆔') if is_spoiler else em
        ch_part = f"{NL}{NL}<blockquote>{em_used} <b>{ch_name}</b></blockquote>"
        extra_part = f"{NL}<blockquote>{extra}</blockquote>" if extra else ""
        base_part = f"{NL}{NL}<blockquote>{base_footer}</blockquote>" if base_footer else ""
        
        # فوتر پروکسی - بین ایموجی کپشن و فوتر رندوم
        proxy_footer = ''
        if (await db.get('proxy_enabled')) == '1':
            proxy_text = await db.get('proxy_text') or 'پروکسیزمون'
            proxy_linked = make_proxy_link(proxy_text)
            proxy_footer = f"{NL}{NL}<blockquote>{proxy_linked}</blockquote>"
        
        allowed = 1024 - tlen(pre) - tlen(extra_part) - tlen(base_part) - tlen(proxy_footer) - tlen(ch_part) - tlen(cap_footer) - 60
        body = truncate_html(body_full, max(200, allowed))
        def build_caption(b):
            if media:
                cb = b + extra_part + cap_footer
            else:
                cb = (f"<tg-spoiler>{b}</tg-spoiler>" if is_spoiler else b) + extra_part + cap_footer
            return pre + cb + proxy_footer + base_part + ch_part
        caption = build_caption(body)
        guard = 0
        while tlen(caption) > 1024 and guard < 10:
            allowed -= 60
            body = truncate_html(body_full, max(100, allowed))
            caption = build_caption(body)
            guard += 1
        path = None
        paths = []
        if media:
            paths = await get_album_paths(source, mid)
            path = paths[0] if paths else None
        if media and len(paths) > 1:
            if has_watermark and paths:
                wm_text = await db.get('watermark_id') or ''
                if wm_text:
                    watermarked_paths = []
                    for p in paths:
                        wm_path = apply_watermark(p, wm_text)
                        watermarked_paths.append(wm_path)
                    paths = watermarked_paths
            ok=False; sent_via='none'
            if not is_spoiler and '<tg-emoji' in caption and os.path.exists('premium_session.session'):
                try:
                    if not premium_client.is_connected(): await premium_client.connect()
                    await premium_client.send_file(channel, paths, caption=caption, parse_mode='html')
                    ok=True; sent_via='album-prem'
                except Exception as e1: PUBLISH_ERR=str(e1)
            if not ok:
                from aiogram.types import InputMediaVideo, InputMediaPhoto
                try:
                    ml=[]
                    for i,p in enumerate(paths):
                        cap=strip_prem(caption) if i==0 else None
                        if p.endswith('.mp4'):
                            ml.append(InputMediaVideo(media=FSInputFile(p), has_spoiler=bool(is_spoiler), caption=cap, parse_mode=(ParseMode.HTML if i==0 else None)))
                        else:
                            ml.append(InputMediaPhoto(media=FSInputFile(p), has_spoiler=bool(is_spoiler), caption=cap, parse_mode=(ParseMode.HTML if i==0 else None)))
                    await bot.send_media_group(channel, ml)
                    ok=True; sent_via='bot-album'
                except Exception as e1: PUBLISH_ERR=str(e1)
            DBG_LIST.append(f"#{pid} album via={sent_via}")
            async with aiosqlite.connect('auto_pub.db') as conn:
                await conn.execute("UPDATE batch_posts SET status='published' WHERE id=?", (pid,))
                await conn.execute("INSERT OR IGNORE INTO published (source, msg_id, published_at) VALUES (?,?,?)", (source, mid, datetime.now().isoformat()))
                await conn.commit()
            return ok
        sent = False
        sent_via = 'none'
        prem_exists = os.path.exists('premium_session.session')
        if is_spoiler and path:
            if has_watermark:
                wm_text = await db.get('watermark_id') or ''
                if wm_text:
                    path = apply_watermark(path, wm_text)
            cap2 = remove_emoji_tags(strip_prem(caption))
            try:
                if path.endswith('.mp4'):
                    await bot.send_animation(channel, FSInputFile(path), caption=cap2, parse_mode=ParseMode.HTML, has_spoiler=True)
                else:
                    await bot.send_photo(channel, FSInputFile(path), caption=cap2, parse_mode=ParseMode.HTML, has_spoiler=True)
                sent = True
                sent_via = 'bot-photo'
            except Exception as e1:
                PUBLISH_ERR = str(e1)
        elif is_spoiler and not path:
            body_html = format_text(text or '', fmt)
            cap_html = remove_emoji_tags(strip_prem(pre)) + '<tg-spoiler>' + body_html + '</tg-spoiler>' + remove_emoji_tags(strip_prem(extra_part)) + remove_emoji_tags(strip_prem(cap_footer)) + remove_emoji_tags(strip_prem(proxy_footer)) + remove_emoji_tags(strip_prem(base_part)) + remove_emoji_tags(strip_prem(ch_part))
            try:
                await bot.send_message(channel, cap_html, parse_mode=ParseMode.HTML)
                sent = True
                sent_via = 'bot-html-spoiler'
            except Exception as e1:
                PUBLISH_ERR = str(e1)
        else:
            # WM_NORMAL - واترمارک برای پست عادی
            if has_watermark and path:
                wm_text = await db.get('watermark_id') or ''
                if wm_text:
                    path = apply_watermark(path, wm_text)
            if '<tg-emoji' in caption and prem_exists:
                for attempt in range(3):
                    try:
                        if not premium_client.is_connected(): await premium_client.connect()
                        if path:
                            await premium_client.send_file(channel, path, caption=caption, parse_mode='html')
                        else:
                            await premium_client.send_message(channel, caption, parse_mode='html')
                        sent = True
                        sent_via = 'premium'
                        break
                    except Exception as e2:
                        PREMIUM_ERR = str(e2)
                        await asyncio.sleep(2)
            if not sent:
                cap2 = strip_prem(caption)
                try:
                    if path:
                        if has_watermark:
                            wm_text = await db.get('watermark_id') or ''
                            if wm_text:
                                path = apply_watermark(path, wm_text)
                        if path.endswith('.mp4'):
                            await bot.send_animation(channel, FSInputFile(path), caption=cap2, parse_mode=ParseMode.HTML)
                        else:
                            await bot.send_photo(channel, FSInputFile(path), caption=cap2, parse_mode=ParseMode.HTML)
                    else:
                        await bot.send_message(channel, cap2, parse_mode=ParseMode.HTML)
                    sent = True
                    sent_via = 'bot'
                except Exception as e1:
                    PUBLISH_ERR = str(e1)
        if not sent:
            plain = re.sub(r'<[^>]+>', '', caption)
            if path:
                await bot.send_photo(channel, FSInputFile(path), caption=plain, has_spoiler=is_spoiler)
            else:
                await bot.send_message(channel, plain)
            sent_via = 'plain'
        DBG_LIST.append(f"#{pid} sp={int(is_spoiler)} cap={int(bool(cap_footer))} via={sent_via}")
        async with aiosqlite.connect('auto_pub.db') as conn:
            await conn.execute("UPDATE batch_posts SET status='published' WHERE id=?", (pid,))
            await conn.execute("INSERT OR IGNORE INTO published (source, msg_id, published_at) VALUES (?,?,?)", (source, mid, datetime.now().isoformat()))
            await conn.commit()
        return True
    except Exception as ex:
        PUBLISH_ERR = str(ex)
        logger.error(f"publish error: {ex}")
        return False

@router.callback_query(F.data == "sched_all")
async def cb_sched_all(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "زمان برای همه پست‌های تایید شده:\nمثال: 16:00 today")
    await state.set_state(States.set_time_all)
    await callback.answer()

@router.message(States.set_time_all)
async def msg_set_time_all(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        time_tok = None; day = 'today'
        for t in parts:
            if ':' in t: time_tok = t
            elif t in ('tomorrow', 'farda', 'فردا'): day = 'tomorrow'
        if not time_tok: raise ValueError('time missing')
        h, mi = map(int, time_tok.split(':'))
        now_ir = datetime.now(ZoneInfo('Asia/Tehran')).replace(tzinfo=None)
        target = now_ir.replace(hour=h, minute=mi, second=0, microsecond=0)
        if day == 'tomorrow': target += timedelta(days=1)
        elif target <= now_ir: target += timedelta(days=1)
        ch = (await db.get('main_channel')).strip()
        try: channel = int(ch)
        except ValueError:
            chat = await bot.get_chat(ch); channel = chat.id
        async with aiosqlite.connect('auto_pub.db') as conn:
            ids = [r[0] for r in await (await conn.execute("SELECT id FROM batch_posts WHERE status='approved'")).fetchall()]
            for pid in ids:
                await conn.execute("INSERT INTO schedules (post_id, scheduled_at, target_chat) VALUES (?,?,?)", (pid, target.isoformat(), channel))
                await conn.execute("UPDATE batch_posts SET status='scheduled' WHERE id=?", (pid,))
            await conn.commit()
        await message.answer(f"✅ {len(ids)} پست برای {target.strftime('%m-%d %H:%M')} زمان‌بندی شد.", reply_markup=menu_kb())
    except Exception as e:
        await message.answer(f"❌ خطا: {e}")
    await state.clear()

@router.callback_query(F.data == "approved_list")
async def cb_approved(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        app = await (await conn.execute("SELECT id, text FROM batch_posts WHERE status='approved' ORDER BY id DESC LIMIT 15")).fetchall()
        sch = await (await conn.execute("SELECT b.id, b.text, s.scheduled_at FROM batch_posts b JOIN schedules s ON s.post_id=b.id ORDER BY s.scheduled_at LIMIT 15")).fetchall()
    lines = ["✅ تایید شده در انتظار انتشار:"] + [f"• #{r[0]} {(r[1] or '')[:35]}" for r in app]
    lines += ["", "📅 زمان‌بندی شده:"] + [f"• #{r[0]} ⏰{r[2][11:16]} {(r[1] or '')[:25]}" for r in sch]
    if not app and not sch: lines = ["لیست خالی است — همه منتشر شده‌اند ✅"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🧹 پاک کردن لیست تایید شده", callback_data="clear_approved")], [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")]])
    await bot.send_message(callback.from_user.id, "\n".join(lines), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "clear_approved")
async def cb_clear_approved(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET status='rejected' WHERE status='approved'")
        await conn.commit()
    await callback.answer("✅ لیست خالی شد.")
    await show_menu(callback.from_user.id)

@router.callback_query(F.data == "schedules")
async def cb_schedules(callback: types.CallbackQuery):
    async with aiosqlite.connect('auto_pub.db') as conn:
        rows = await (await conn.execute("SELECT s.id, s.scheduled_at, b.text FROM schedules s JOIN batch_posts b ON b.id=s.post_id ORDER BY s.scheduled_at")).fetchall()
    if not rows:
        await bot.send_message(callback.from_user.id, "⚠️ خالی است.", reply_markup=menu_kb())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🚀 {r[1][11:16]} {(r[2] or '')[:15]}", callback_data=f"now_sch_{r[0]}"), InlineKeyboardButton(text="❌", callback_data=f"del_sch_{r[0]}")] for r in rows])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🚀 انتشار همه", callback_data="pub_all_sch")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu")])
        await bot.send_message(callback.from_user.id, "📅 زمان‌بندی‌ها:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("del_sch_"))
async def cb_del_sch(callback: types.CallbackQuery):
    sid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
        await conn.commit()
    await callback.answer("✅ حذف شد.")

@router.callback_query(F.data.startswith("now_sch_"))
async def cb_now_sch(callback: types.CallbackQuery):
    await callback.answer("در حال انتشار...")
    sid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT post_id FROM schedules WHERE id=?", (sid,))).fetchone()
        await conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
        await conn.commit()
    ok = False
    if row: ok = await do_publish(row[0])
    await bot.send_message(callback.from_user.id, "✅ منتشر شد." if ok else "❌ خطا.", reply_markup=menu_kb())

@router.callback_query(F.data == "pub_all_sch")
async def cb_pub_all_sch(callback: types.CallbackQuery):
    await callback.answer("در حال انتشار...")
    asyncio.create_task(publish_all_scheduled(callback.from_user.id))

async def publish_all_scheduled(chat_id):
    global PUBLISH_ERR, PREMIUM_ERR, DBG
    try:
        async with aiosqlite.connect('auto_pub.db') as conn:
            rows = await (await conn.execute("SELECT id, post_id FROM schedules ORDER BY id")).fetchall()
        n = 0
        for sid, pid in rows:
            if await do_publish(pid): n += 1
            async with aiosqlite.connect('auto_pub.db') as conn:
                await conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
                await conn.commit()
        msg = f"✅ {n} از {len(rows)} پست منتشر شد."
        if n < len(rows): msg += f"\n❌ خطا: {PUBLISH_ERR or 'نامشخص'}"
        elif PREMIUM_ERR: msg += f"\n⚠️ اکانت پریمیوم نفرستاد ({PREMIUM_ERR[:150]}) — بدون ایموجی پریمیوم. اکانت پریمیوم را عضو کانال کن!"
        try: await wait_msg.delete()
        except Exception: pass
        try: await status_msg.delete()
        except Exception: pass
        await cleanup_chat(chat_id)
        await show_menu(chat_id, msg + "\n\n🤖 ربات انتشار خودکار")
    except Exception as e:
        PUBLISH_ERR = str(e)
        logger.error(f"publish_all_sch: {e}")
        await bot.send_message(chat_id, f"❌ خطا: {e}", reply_markup=menu_kb())


from aiogram.filters import StateFilter

@router.callback_query(F.data == "set_watermark_id")
async def cb_set_watermark_id(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text("🆔 آیدی واترمارک را ارسال کنید (مثال: @mychannel):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]]))
    except Exception:
        await bot.send_message(callback.from_user.id, "🆔 آیدی واترمارک را ارسال کنید (مثال: @mychannel):")
    await state.set_state('waiting_watermark_id')
    await callback.answer()

@router.message(F.text, StateFilter('waiting_watermark_id'))
async def msg_set_watermark_id(message: types.Message, state: FSMContext):
    await db.set('watermark_id', message.text.strip())
    await message.answer(f"✅ آیدی واترمارک ذخیره شد: {message.text.strip()}", reply_markup=main_menu_kb())
    await state.clear()

@router.callback_query(F.data.startswith("toggle_watermark_"))
async def cb_toggle_watermark(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        try:
            await conn.execute("ALTER TABLE batch_posts ADD COLUMN has_watermark INTEGER DEFAULT 0")
            await conn.commit()
        except Exception:
            pass
        row = await (await conn.execute("SELECT has_watermark, is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
        current = row[0] if row and row[0] else 0
        new_status = 0 if current else 1
        is_spoiler = bool(row[1]) if row else False
        await conn.execute("UPDATE batch_posts SET has_watermark=? WHERE id=?", (new_status, pid))
        await conn.commit()
    try:
        await callback.message.edit_reply_markup(reply_markup=preview_kb(pid, is_spoiler, new_status))
    except Exception:
        pass
    await callback.answer(f"واترمارک {'روشن ✅' if new_status else 'خاموش ❌'}")

async def scheduler():
    while True:
        try:
            async with aiosqlite.connect('auto_pub.db') as conn:
                due = await (await conn.execute("SELECT id, post_id FROM schedules WHERE scheduled_at <= ?", (datetime.now(ZoneInfo('Asia/Tehran')).replace(tzinfo=None).isoformat(),))).fetchall()
                for sid, pid in due:
                    await do_publish(pid)
                    await conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
                await conn.commit()
        except Exception as e:
            logger.error(f"scheduler: {e}")
        await asyncio.sleep(30)

async def auto_batch():
    while True:
        lo = int(await db.get('min_interval')); hi = int(await db.get('max_interval'))
        await asyncio.sleep(random.randint(lo, hi) * 60)
        for aid in ADMINS:
            try: await generate_batch(aid)
            except Exception as e: logger.error(f"auto batch: {e}")

@router.callback_query(F.data == "set_cap_emoji_count")
async def cb_set_cap_emoji_count(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "تعداد ایموجی‌های کپشن که رندوم انتخاب شوند (مثلا 5):")
    await state.set_state(States.set_cap_emoji_count)
    await callback.answer()

@router.message(States.set_cap_emoji_count)
async def msg_set_cap_emoji_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count < 1: count = 1
        await db.set('cap_emoji_count', count)
        await message.answer(f"✅ ذخیره شد: {count} ایموجی.", reply_markup=menu_kb())
    except Exception:
        await message.answer("❌ عدد نامعتبر.")
    await state.clear()

def strip_links(t):
    if not t: return ''
    # حذف لینک‌های http/https
    t = re.sub(r'https?://\S+', '', t)
    # حذف t.me/...
    t = re.sub(r't\.me/\S+', '', t, flags=re.I)
    # حذف www.xxx
    t = re.sub(r'www\.\S+', '', t, flags=re.I)
    # حذف دامنه‌های com/net/org/ir بدون پروتکل (مثل example.com)
    t = re.sub(r'\b[A-Za-z0-9.-]+\.(com|net|org|ir|io|co|biz|info|me|xyz|top)\b', '', t, flags=re.I)
    # حذف یوزرنیم‌های @
    t = re.sub(r'@[A-Za-z0-9_]{4,}', '', t)
    # حذف فاصله‌های اضافی
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def preview_kb(pid, is_spoiler, has_watermark=0):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_{pid}"), InlineKeyboardButton(text="❌ رد", callback_data=f"reject_{pid}")],
        [InlineKeyboardButton(text=f"⚠️ اسپویلر: {'روشن ✅' if is_spoiler else 'خاموش ❌'}", callback_data=f"toggle_spoiler_{pid}"), InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"editprev_{pid}")],
        [InlineKeyboardButton(text="🧹 حذف لینک/یوزر", callback_data=f"striplinks_{pid}")],
        [InlineKeyboardButton(text=f"💧 واترمارک: {'روشن ✅' if has_watermark else 'خاموش ❌'}", callback_data=f"toggle_watermark_{pid}")],
    ])

@router.callback_query(F.data.startswith("toggle_spoiler_"))
async def cb_toggle_spoiler(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
        new_status = 0 if (row and row[0]) else 1
        await conn.execute("UPDATE batch_posts SET is_spoiler=? WHERE id=?", (new_status, pid))
        await conn.commit()
    try:
        await callback.message.edit_reply_markup(reply_markup=preview_kb(pid, new_status))
    except Exception:
        pass
    await callback.answer(f"اسپویلر {'روشن ✅' if new_status else 'خاموش ❌'}")

@router.callback_query(F.data.startswith("toggle_watermark_"))
async def cb_toggle_watermark(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[2])
    async with aiosqlite.connect('auto_pub.db') as conn:
        try:
            await conn.execute("ALTER TABLE batch_posts ADD COLUMN has_watermark INTEGER DEFAULT 0")
            await conn.commit()
        except:
            pass
        row = await (await conn.execute("SELECT has_watermark FROM batch_posts WHERE id=?", (pid,))).fetchone()
        current = row[0] if row and row[0] else 0
        new_status = 0 if current else 1
        await conn.execute("UPDATE batch_posts SET has_watermark=? WHERE id=?", (new_status, pid))
        await conn.commit()
    try:
        row2 = await (await conn.execute("SELECT is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
        is_spoiler = bool(row2[0]) if row2 else False
        await callback.message.edit_reply_markup(reply_markup=preview_kb(pid, is_spoiler, new_status))
    except Exception:
        pass
    await callback.answer(f"واترمارک {'روشن ✅' if new_status else 'خاموش ❌'}")

@router.callback_query(F.data == "set_sp_id_emoji")
async def cb_set_sp_id_emoji(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "یک ایموجی ساده برای ایدی پست‌های اسپویلردار بفرست (مثل 🆔):")
    await state.set_state(States.set_sp_id_emoji)
    await callback.answer()

@router.message(States.set_sp_id_emoji)
async def msg_set_sp_id_emoji(message: types.Message, state: FSMContext):
    await db.set('sp_id_emoji', message.text.strip())
    await message.answer(f"✅ ذخیره شد: {message.text.strip()}", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data.startswith("striplinks_"))
async def cb_striplinks(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT text FROM batch_posts WHERE id=?", (pid,))).fetchone()
        if row and row[0]:
            new_text = strip_links(row[0])
            await conn.execute("UPDATE batch_posts SET text=? WHERE id=?", (new_text, pid))
            await conn.commit()
    await callback.answer("✅ لینک/یوزر حذف شد.")
    try:
        await callback.message.edit_reply_markup(reply_markup=preview_kb(pid, False))
    except Exception:
        pass

async def show_pre_view(chat_id):
    fixed = (await db.get('pre_fixed')) or ''
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش", callback_data="pfix_edit"), InlineKeyboardButton(text="🗑 حذف", callback_data="pfix_del")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")],
    ])
    await bot.send_message(chat_id, f"🎯 ایموجی ثابت اول کپشن:\n{fixed or '(خالی)'}", reply_markup=kb)

@router.callback_query(F.data == "set_pre_fixed")
async def cb_set_pre_fixed(callback: types.CallbackQuery):
    await show_pre_view(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "pfix_edit")
async def cb_pfix_edit(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "ایموجی/استیکر ثابت اول کپشن را بفرست:")
    await state.set_state(States.set_pre_fixed)
    await callback.answer()

@router.callback_query(F.data == "pfix_del")
async def cb_pfix_del(callback: types.CallbackQuery):
    await db.set('pre_fixed', '')
    await callback.answer("✅ حذف شد.")
    await show_pre_view(callback.from_user.id)

@router.message(States.set_pre_fixed)
async def msg_set_pre_fixed(message: types.Message, state: FSMContext):
    txt = message.text or ''
    tags = []
    if message.entities:
        for ent in message.entities:
            if ent.type == 'custom_emoji':
                sub = txt[ent.offset:ent.offset+ent.length]
                tags.append(f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{sub}</tg-emoji>')
    val = ''.join(tags) if tags else txt.strip()
    await db.set('pre_fixed', val)
    await message.answer("✅ ایموجی ثابت اول کپشن ذخیره شد.", reply_markup=menu_kb())
    await state.clear()

@router.callback_query(F.data == "set_pre_count")
async def cb_set_pre_count(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "تعداد ایموجی رندوم اول کپشن (مثلا 3):")
    await state.set_state(States.set_pre_count)
    await callback.answer()

@router.message(States.set_pre_count)
async def msg_set_pre_count(message: types.Message, state: FSMContext):
    try:
        n = int(message.text)
        if n < 0: n = 0
        await db.set('pre_count', n)
        await message.answer(f"✅ ذخیره شد: {n} ایموجی رندوم اول کپشن.", reply_markup=menu_kb())
    except Exception:
        await message.answer("❌ عدد نامعتبر.")
    await state.clear()

@router.callback_query(F.data == "set_sp_pre")
async def cb_set_sp_pre(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "قلب/ایموجی اول کپشن پست‌های اسپویلردار را بفرست (مثل ❤️🩵🩷):")
    await state.set_state(States.set_sp_pre)
    await callback.answer()

@router.message(States.set_sp_pre)
async def msg_set_sp_pre(message: types.Message, state: FSMContext):
    await db.set('sp_pre', (message.text or '').strip())
    await message.answer("✅ قلب اول کپشن اسپویلر ذخیره شد.", reply_markup=menu_kb())
    await state.clear()

async def show_rand_view(chat_id):
    pool = (await db.get('rand_footer')) or ''
    items = [x for x in pool.split('|||||') if x.strip()]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن", callback_data="add_rand_footer"), InlineKeyboardButton(text="🗑 حذف همه", callback_data="del_rand_footer")],
        [InlineKeyboardButton(text="⬅ بازگشت", callback_data="settings")],
    ])
    disp = chr(10).join(f"{i+1}. {re.sub('<[^>]+>','',x)}" for i,x in enumerate(items[:20]))
    await bot.send_message(chat_id, f"🎲 فوترهای رندوم ({len(items)}):\n{disp or '(خالی)'}", reply_markup=kb)

@router.callback_query(F.data == "set_rand_footer")
async def cb_set_rand_footer(callback: types.CallbackQuery, state: FSMContext):
    await show_rand_view(callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "add_rand_footer")
async def cb_add_rand_footer(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback.from_user.id, "متن/ایموجی جدید بفرست (هر خط = یک گزینه):")
    await state.set_state(States.set_rand_footer)
    await callback.answer()

@router.callback_query(F.data == "del_rand_footer")
async def cb_del_rand_footer(callback: types.CallbackQuery, state: FSMContext):
    await db.set('rand_footer', '')
    await show_rand_view(callback.from_user.id)
    await callback.answer()

@router.message(States.set_rand_footer)
async def msg_set_rand_footer(message: types.Message, state: FSMContext):
    txt = message.text or ''
    _old = (await db.get('rand_footer')) or ''
    items = [x for x in _old.split('|||||') if x.strip()]
    for line in txt.split('\n'):
        if not line.strip(): continue
        out = line
        if message.entities:
            for ent in message.entities:
                if ent.type == 'custom_emoji':
                    sub = txt[ent.offset:ent.offset+ent.length]
                    if sub in out:
                        out = out.replace(sub, f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{sub}</tg-emoji>', 1)
        items.append(out.strip())
    await db.set('rand_footer', '|||||'.join(items))
    await state.clear()
    await show_rand_view(message.chat.id)


def edit_menu_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 فوتر اضافه", callback_data=f"addfoot_{pid}"), InlineKeyboardButton(text="✏️ متن کپشن", callback_data=f"editcap_{pid}")],
        [InlineKeyboardButton(text="✅ اوکی", callback_data=f"okprev_{pid}"), InlineKeyboardButton(text="🔙 انصراف", callback_data=f"backprev_{pid}")],
    ])

async def update_preview(pid, kb):
    info = EDIT_MSG.get(pid)
    if not info: return
    cid, mid, has_media = info
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT text, is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
    if not row: return
    txt, is_sp = row
    try:
        if has_media:
            await bot.edit_message_caption(chat_id=cid, message_id=mid, caption=(txt or None), reply_markup=kb)
        else:
            await bot.edit_message_text(chat_id=cid, message_id=mid, text=(txt or '(بدون متن)'), reply_markup=kb)
    except Exception as e:
        logger.error(f"update_preview: {e}")

@router.callback_query(F.data.startswith("editprev_"))
async def cb_editprev(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    EDIT_MSG[pid] = (callback.from_user.id, callback.message.message_id, bool(callback.message.photo or callback.message.animation or callback.message.video or callback.message.document))
    await update_preview(pid, edit_menu_kb(pid))
    await callback.answer()

@router.callback_query(F.data.startswith("okprev_"))
async def cb_okprev(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
    is_sp = bool(row[0]) if row else False
    await update_preview(pid, preview_kb(pid, is_sp))
    await callback.answer()

@router.callback_query(F.data.startswith("backprev_"))
async def cb_backprev(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT is_spoiler FROM batch_posts WHERE id=?", (pid,))).fetchone()
    is_sp = bool(row[0]) if row else False
    await update_preview(pid, preview_kb(pid, is_sp))
    await callback.answer()

@router.callback_query(F.data.startswith("addfoot_"))
async def cb_addfoot(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    EDIT_MSG[pid] = (callback.from_user.id, callback.message.message_id, bool(callback.message.photo or callback.message.animation or callback.message.video or callback.message.document))
    await state.update_data(pid=pid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ اوکی", callback_data=f"okprev_{pid}"), InlineKeyboardButton(text="🔙 انصراف", callback_data=f"backprev_{pid}")]])
    try:
        if (callback.message.photo or callback.message.animation or callback.message.video or callback.message.document):
            await callback.message.edit_caption(caption="📝 متن/ایموجی فوتر را بفرست (به انتهای کپشن اضافه می‌شود):", reply_markup=kb)
        else:
            await callback.message.edit_text("📝 متن/ایموجی فوتر را بفرست (به انتهای کپشن اضافه می‌شود):", reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, "📝 متن/ایموجی فوتر را بفرست:", reply_markup=kb)
    await state.set_state(States.set_prev_footer)
    await callback.answer()

@router.callback_query(F.data.startswith("editcap_"))
async def cb_editcap(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    EDIT_MSG[pid] = (callback.from_user.id, callback.message.message_id, bool(callback.message.photo or callback.message.animation or callback.message.video or callback.message.document))
    await state.update_data(pid=pid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ اوکی", callback_data=f"okprev_{pid}"), InlineKeyboardButton(text="🔙 انصراف", callback_data=f"backprev_{pid}")]])
    try:
        if (callback.message.photo or callback.message.animation or callback.message.video or callback.message.document):
            await callback.message.edit_caption(caption="✏️ متن جدید کپشن را بفرست (جایگزین می‌شود):", reply_markup=kb)
        else:
            await callback.message.edit_text("✏️ متن جدید کپشن را بفرست (جایگزین می‌شود):", reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, "✏️ متن جدید کپشن را بفرست:", reply_markup=kb)
    await state.set_state(States.set_prev_caption)
    await callback.answer()

@router.message(States.set_prev_footer)
async def msg_prev_footer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get('pid')
    added = extract_tags(message)
    async with aiosqlite.connect('auto_pub.db') as conn:
        row = await (await conn.execute("SELECT foot FROM batch_posts WHERE id=?", (pid,))).fetchone()
        old = row[0] or ''
        new = (old + '\n' + added).strip() if old else added
        await conn.execute("UPDATE batch_posts SET foot=? WHERE id=?", (new, pid))
        await conn.commit()
    await state.clear()
    try: await message.delete()
    except Exception: pass
    await update_preview(pid, edit_menu_kb(pid))

@router.message(States.set_prev_caption)
async def msg_prev_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get('pid')
    new = extract_tags(message)
    async with aiosqlite.connect('auto_pub.db') as conn:
        await conn.execute("UPDATE batch_posts SET text=? WHERE id=?", (new, pid))
        await conn.commit()
    await state.clear()
    try: await message.delete()
    except Exception: pass
    await update_preview(pid, edit_menu_kb(pid))

async def main():
    await db.init()
    await telethon_client.start()
    if os.path.exists('premium_session.session'):
        try:
            await premium_client.start()
            logger.info("premium client ready")
        except Exception as e:
            logger.error(f"premium start: {e}")
    async with aiosqlite.connect('auto_pub.db') as conn:
        try:
            await conn.execute("ALTER TABLE sources ADD COLUMN grp TEXT DEFAULT 'day'")
        except Exception: pass
        await conn.commit()
    asyncio.create_task(scheduler())
    asyncio.create_task(proxy_scheduler())
    # asyncio.create_task(auto_batch())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
