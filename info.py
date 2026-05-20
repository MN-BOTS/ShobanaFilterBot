import re
from os import environ

id_pattern = re.compile(r'^\b[+-]?\d+\b')

# ⚙️ Bot Credentials & Configuration
API_ID = int(environ.get('API_ID', ''))
API_HASH = environ.get('API_HASH', '')
BOT_TOKEN = environ.get('BOT_TOKEN', '')

# 👑 Admin & Users Settings
ADMINS = [int(admin) if id_pattern.search(admin) else admin for admin in environ.get('ADMINS', '').split()]
AUTH_USERS = [int(user) if id_pattern.search(user) else user for user in environ.get('AUTH_USERS', '').split()]
AUTH_GROUPS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('AUTH_GROUPS', '').split()]

# 🗄️ Database Config
DATABASE_URI = environ.get('DATABASE_URI', "")
DATABASE_NAME = environ.get('DATABASE_NAME', "Cluster0")
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'Telegram_files')

# 📢 Links & Channel Promotion Settings
BRANDING_LINK = "https://t.me/Moviepornindia"
FORCE_SUB = environ.get('FORCE_SUB', 'Moviepornindia')
SUPPORT_CHAT = "Moviepornindia"

# 🖼️ Media & UI Settings
START_IMG = environ.get('START_IMG', 'https://graph.org/file/7eb62c64db3be373b9e4b.jpg')
PICS = environ.get('PICS', 'https://graph.org/file/7eb62c64db3be373b9e4b.jpg').split()

# ⚙️ Custom Captions & Templates
CUSTOM_FILE_CAPTION = environ.get('CUSTOM_FILE_CAPTION', "📁 <b>File Name:</b> {file_name}\n\n⚙️ <b>Size:</b> {file_size}\n\n🍿 <b>Join Here:</b> @Moviepornindia")
BATCH_FILE_CAPTION = environ.get('BATCH_FILE_CAPTION', "📁 <b>File Name:</b> {file_name}\n\n⚙️ <b>Size:</b> {file_size}\n\n🍿 <b>Join Here:</b> @Moviepornindia")
IMDB_TEMPLATE = environ.get('IMDB_TEMPLATE', "<b>Title:</b> {title}\n<b>Rating:</b> {rating}")

# 🛠️ Feature Toggles & Extra Variables
P_TTI_SHOW_OFF = environ.get('P_TTI_SHOW_OFF', "False") == "True"
IMDB = environ.get('IMDB', "False") == "True"
SINGLE_BUTTON = environ.get('SINGLE_BUTTON', "True") == "True"
SPELL_CHECK_REPLY = environ.get('SPELL_CHECK_REPLY', "True") == "True"
MAX_LIST_ELM = int(environ.get('MAX_LIST_ELM', 5))
INDEX_REQ_CHANNEL = int(environ.get('INDEX_REQ_CHANNEL', '-100'))
PROTECT_CONTENT = environ.get('PROTECT_CONTENT', "False") == "True"
PUBLIC_FILE_STORE = environ.get('PUBLIC_FILE_STORE', "False") == "True"
POSTGRES_STORAGE_LIMIT_BYTES = int(environ.get('POSTGRES_STORAGE_LIMIT_BYTES', 536870912))
REQUEST_FSUB_MODE = environ.get('REQUEST_FSUB_MODE', "False") == "True"
HYPER_MODE = environ.get('HYPER_MODE', "False") == "True"
USE_CAPTION_FILTER = False
LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-100'))

# 🚨 All Missing Variables Fix
MELCOW_NEW_USERS = environ.get('MELCOW_NEW_USERS', "True") == "True"
SESSION = environ.get('SESSION', 'Media_search')
LOG_STR = environ.get('LOG_STR', '')
KEEP_ALIVE_URL = environ.get('KEEP_ALIVE_URL', '')
DEFAULT_AUTH_CHANNELS = [int(ch) for ch in environ.get('DEFAULT_AUTH_CHANNELS', '').split()]
LONG_IMDB_DESCRIPTION = environ.get('LONG_IMDB_DESCRIPTION', "False") == "True"
MDISK_API = environ.get('MDISK_API', "")
SHORTENER_API = environ.get('SHORTENER_API', "")
SHORTENER_WEBSITE = environ.get('SHORTENER_WEBSITE', "")

# 📡 Channels Config
CHANNELS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('CHANNELS', '').split()]
FILE_CHANNELS = [int(ch) for ch in environ.get('FILE_CHANNELS', '').split()]
FILE_STORE_CHANNEL = [int(ch) for ch in environ.get('FILE_STORE_CHANNEL', '').split()]
FILE_CHANNEL_SEND_MODE = environ.get('FILE_CHANNEL_SEND_MODE', '0')
FILE_CHANNEL_SENDING_MODE = environ.get('FILE_CHANNEL_SENDING_MODE', '0')
FILE_AUTO_DELETE_SECONDS = int(environ.get('FILE_AUTO_DELETE_SECONDS', '0'))
