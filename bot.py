import os
import logging
import routeros_api
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext

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

# Setup Logging untuk Debugging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Debugging: Log daftar Chat ID yang diizinkan saat bot dijalankan
logger.info(f"TELEGRAM_CHATID yang terbaca: {raw_chat_ids}")
logger.info(f"Chat ID yang diizinkan: {AUTHORIZED_CHAT_IDS}")

# Fungsi untuk memeriksa apakah user diizinkan
def is_authorized(update: Update) -> bool:
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    logger.info(f"Chat ID {chat_id} mencoba mengakses bot.")

    if chat_id in AUTHORIZED_CHAT_IDS:
        logger.info(f"Chat ID {chat_id} diizinkan.")
        return True
    else:
        logger.warning(f"Chat ID {chat_id} DITOLAK!")
        return False

# Fungsi untuk mengambil daftar user PPPoE dari MikroTik
def get_pppoe_users():
    logger.info("Mengambil daftar user PPPoE dari MikroTik...")
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
        connection.disconnect()

        logger.info("Berhasil mengambil daftar user PPPoE.")
        if not users:
            return "❌ Tidak ada user PPPoE yang terdaftar."

        user_list = "\n".join([f"{user['name']} - {user.get('profile', 'No Profile')}" for user in users])
        return f"📋 Daftar User PPPoE:\n{user_list}"
    except Exception as e:
        logger.error(f"Error saat mengambil user PPPoE: {str(e)}")
        return f"⚠️ Error: {str(e)}"

# Fungsi untuk menampilkan menu dengan tombol
async def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    logger.info(f"Perintah /start diterima dari Chat ID {chat_id}")

    if not is_authorized(update):
        await update.message.reply_text("🚫 Anda tidak memiliki izin untuk menggunakan bot ini.")
        logger.warning(f"Chat ID {chat_id} ditolak akses!")
        return

    keyboard = [[InlineKeyboardButton("🔍 Cek User PPPoE", callback_data="cekuser")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 Pilih menu di bawah:", reply_markup=reply_markup)

# Fungsi untuk menangani tombol
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    logger.info(f"Tombol diklik oleh Chat ID {chat_id} dengan data: {query.data}")

    if not is_authorized(update):
        await query.answer("🚫 Anda tidak memiliki izin untuk menggunakan bot ini.", show_alert=True)
        logger.warning(f"Chat ID {chat_id} ditolak akses!")
        return

    await query.answer()
    if query.data == "cekuser":
        user_list = get_pppoe_users()
        await query.message.reply_text(user_list)

# Main Program
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN belum dikonfigurasi di config.env")
        return

    logger.info("🚀 Memulai bot Telegram...")

    if not AUTHORIZED_CHAT_IDS:
        logger.warning("⚠️ AUTHORIZED_CHAT_IDS kosong atau tidak diatur dengan benar!")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Tambahkan command handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Mulai bot
    logger.info("✅ Bot sedang berjalan...")
    app.run_polling()

if __name__ == '__main__':
    main()
