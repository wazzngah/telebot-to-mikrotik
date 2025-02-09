import os
import logging
import routeros_api
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters

# Load konfigurasi dari config.env
load_dotenv("config.env")

# Ambil konfigurasi dari environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MIKROTIK_IP = os.getenv("MIKROTIK_IP")
MIKROTIK_PORT = int(os.getenv("MIKROTIK_PORT", 8728))
MIKROTIK_USER = os.getenv("MIKROTIK_USER")
MIKROTIK_PASS = os.getenv("MIKROTIK_PASS")

# Ambil daftar Chat ID yang diizinkan dan filter hanya angka
raw_chat_ids = os.getenv("TELEGRAM_CHATID", "")
AUTHORIZED_CHAT_IDS = [
    int(chat_id) for chat_id in raw_chat_ids.split(",") if chat_id.strip().isdigit()
]

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"Chat ID yang diizinkan: {AUTHORIZED_CHAT_IDS}")

def is_authorized(update: Update) -> bool:
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    return chat_id in AUTHORIZED_CHAT_IDS

def get_pppoe_stats():
    try:
        connection = routeros_api.RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_PORT,
            plaintext_login=True
        )
        api = connection.get_api()
        users = api.get_resource('/ppp/secret').get()
        active_users = api.get_resource('/ppp/active').get()
        connection.disconnect()

        total_users = len(users)
        online_users = len(active_users)
        offline_users = total_users - online_users

        return f"\n📊 Statistik User PPPoE:\n🔹 Online: {online_users}\n🔻 Offline: {offline_users}\n📌 Total: {total_users}"
    except Exception as e:
        logger.error(f"Error mengambil statistik PPPoE: {str(e)}")
        return f"⚠️ Error: {str(e)}"

def get_profiles():
    try:
        connection = routeros_api.RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_PORT,
            plaintext_login=True
        )
        api = connection.get_api()
        profiles = api.get_resource('/ppp/profile').get()
        connection.disconnect()
        return [profile['name'] for profile in profiles]
    except Exception as e:
        logger.error(f"Error mengambil daftar profil: {str(e)}")
        return []

async def start(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update):
        await update.message.reply_text("🚫 Anda tidak memiliki izin untuk menggunakan bot ini.")
        return
    keyboard = [
        [InlineKeyboardButton("📊 Cek Statistik User", callback_data="cekstats")],
        [InlineKeyboardButton("➕ Tambah User", callback_data="tambahuser")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 Pilih menu di bawah:", reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_authorized(update):
        await query.answer("🚫 Anda tidak memiliki izin untuk menggunakan bot ini.", show_alert=True)
        return
    await query.answer()
    if query.data == "cekstats":
        stats = get_pppoe_stats()
        await query.message.reply_text(stats)
    elif query.data == "tambahuser":
        await query.message.reply_text("📝 Masukkan username untuk user baru:")
        context.user_data['step'] = 'username'

async def message_handler(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update):
        await update.message.reply_text("🚫 Anda tidak memiliki izin untuk menggunakan bot ini.")
        return
    step = context.user_data.get('step')
    if step == 'username':
        context.user_data['username'] = update.message.text
        await update.message.reply_text("🔑 Masukkan password untuk user baru:")
        context.user_data['step'] = 'password'
    elif step == 'password':
        context.user_data['password'] = update.message.text
        profiles = get_profiles()
        if not profiles:
            await update.message.reply_text("⚠️ Gagal mengambil daftar profil.")
            return
        keyboard = [[InlineKeyboardButton(profile, callback_data=f"profile_{profile}")] for profile in profiles]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📜 Pilih profil:", reply_markup=reply_markup)
        context.user_data['step'] = 'profile'
    elif step == 'confirm':
        if update.message.text.lower() == 'ya':
            try:
                connection = routeros_api.RouterOsApiPool(
                    MIKROTIK_IP, username=MIKROTIK_USER, password=MIKROTIK_PASS, port=MIKROTIK_PORT, plaintext_login=True
                )
                api = connection.get_api()
                api.get_resource('/ppp/secret').add(
                    name=context.user_data['username'],
                    password=context.user_data['password'],
                    profile=context.user_data['profile'],
                    service="pppoe"
                )
                connection.disconnect()
                await update.message.reply_text("✅ User berhasil ditambahkan!")
            except Exception as e:
                logger.error(f"Error menambahkan user: {str(e)}")
                await update.message.reply_text(f"⚠️ Gagal menambahkan user: {str(e)}")
        else:
            await update.message.reply_text("❌ Proses dibatalkan.")
        context.user_data.clear()

async def profile_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    profile_selected = query.data.replace("profile_", "")

    # ✅ Tambahkan log untuk debugging
    logger.info(f"Profil dipilih: {profile_selected}")
    
    context.user_data['profile'] = profile_selected

    # ✅ Pastikan query dijawab agar tidak ada timeout dari Telegram
    await query.answer("Profil dipilih!")

    # ✅ Kirim konfirmasi ke user
    username = context.user_data.get('username', 'N/A')
    password = context.user_data.get('password', 'N/A')
    
    text_konfirmasi = (
        f"⚡ Konfirmasi penambahan user:\n"
        f"👤 Username: {username}\n"
        f"🔑 Password: {password}\n"
        f"📜 Profile: {profile_selected}\n\n"
        f"Ketik *ya* untuk konfirmasi, atau *tidak* untuk batal."
    )

    await query.message.reply_text(text_konfirmasi, parse_mode="Markdown")
    context.user_data['step'] = 'confirm'


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ✅ Pastikan `profile_handler` ditangani duluan sebelum `button_handler`
    app.add_handler(CallbackQueryHandler(profile_handler, pattern=r"^profile_.*"))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.run_polling()

if __name__ == '__main__':
    main()
