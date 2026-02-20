import re
from os import environ
from Script import script
from time import time

id_pattern = re.compile(r'^.\d+$')

def is_enabled(value, default):
    if value.lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif value.lower() in ["false", "no", "0", "disable", "n"]:
        return False
    else:
        return default

#Bot information
SESSION = environ.get('SESSION', 'Media_search')
API_ID = int(environ.get('API_ID', ''))
API_HASH = environ.get('API_HASH', '')
BOT_TOKEN = environ.get('BOT_TOKEN', '')

# Keep-Alive URL
KEEP_ALIVE_URL = environ.get("KEEP_ALIVE_URL", "https://burning-brittney-leech2-3bc21fb5.koyeb.app/")  # <-- Add this line
#hyper link
HYPER_MODE = bool(environ.get('HYPER_MODE', False))
#request fsub
REQUEST_FSUB_MODE = bool(environ.get('REQUEST_FSUB_MODE', True))
# Bot settings
BOT_START_TIME = time()
CACHE_TIME = int(environ.get('CACHE_TIME', 300))
USE_CAPTION_FILTER = bool(environ.get('USE_CAPTION_FILTER', False))
PICS = (environ.get('PICS', 'https://graph.org/file/2ed90a79eb533d86f8a0f.jpg https://graph.org/file/a0da24dacf4b7bec376a3.jpg https://graph.org/file/457aa9d0e485925088be6.jpg https://graph.org/file/041f7b57c6950070ba16e.jpg https://graph.org/file/f36511f6042d74d95b5df.jpg https://graph.org/file/a30d30b3bc49bd8745533.jpg https://graph.org/file/ce71502cf614059ce1de5.jpg')).split()

# Admins, Channels & Users
ADMINS = [int(admin) if id_pattern.search(admin) else admin for admin in environ.get('ADMINS', '1892771262').split()]
CHANNELS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('CHANNELS', '-1002490892111 -1002097504396').split()]
auth_users = [int(user) if id_pattern.search(user) else user for user in environ.get('AUTH_USERS', '').split()]
AUTH_USERS = (auth_users + ADMINS) if auth_users else []
auth_grp = environ.get('AUTH_GROUP')
DEFAULT_AUTH_CHANNELS = [int(x) for x in environ.get("AUTH_CHANNEL", "").split() if x.lstrip('-').isdigit()]
AUTH_GROUPS = [int(ch) for ch in auth_grp.split()] if auth_grp else None

# Database information
DATABASE_URI = environ.get('DATABASE_URI', "")
DATABASE_NAME = environ.get('DATABASE_NAME', "Cluster0")
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'mn_files')
SQLDB = environ.get('SQLDB', environ.get('TURSO_DATABASE_URL', ""))
TURSO_DATABASE_URL = environ.get('TURSO_DATABASE_URL', SQLDB)
TURSO_AUTH_TOKEN = environ.get('TURSO_AUTH_TOKEN', "")
TURSO_MAX_DB_BYTES = int(environ.get('TURSO_MAX_DB_BYTES', str(5 * 1024 * 1024 * 1024)))

# File Channel Settings
FILE_CHANNELS = [int(ch) for ch in environ.get('FILE_CHANNELS', '-1002831639976 -1002607076908 -1002869981026').split()]
FILE_CHANNEL_SENDING_MODE = is_enabled(environ.get('FILE_CHANNEL_SENDING_MODE', 'False'), False)
FILE_AUTO_DELETE_SECONDS = int(environ.get('FILE_AUTO_DELETE_SECONDS', 3600))  # Default: 1 hour

# Others
LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-1002704640995'))
SUPPORT_CHAT = environ.get('SUPPORT_CHAT', 'mnbots_support')
P_TTI_SHOW_OFF = is_enabled((environ.get('P_TTI_SHOW_OFF', 'False')), False)
IMDB = is_enabled((environ.get('IMDB', 'False')), False)
SINGLE_BUTTON = is_enabled((environ.get('SINGLE_BUTTON', 'True')), True)
CUSTOM_FILE_CAPTION = environ.get("CUSTOM_FILE_CAPTION", f"{script.CUSTOM_FILE_CAPTION}") 
BATCH_FILE_CAPTION = environ.get("BATCH_FILE_CAPTION", "📂 <em>File Name</em>: <code>{file_name}</code>\n\n ♻ <em>File Size</em>:{file_size} \n\n <b><i>Latest Movies -</i> </b>")
IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", "🏷 𝖳𝗂𝗍𝗅𝖾: <a href={url}>{title}</a> \n🔮 𝖸𝖾𝖺𝗋: {year} \n⭐️ 𝖱𝖺𝗍𝗂𝗇𝗀𝗌: {rating}/ 10 \n🎭 𝖦𝖾𝗇𝖾𝗋𝗌: {genres}")
LONG_IMDB_DESCRIPTION = is_enabled(environ.get("LONG_IMDB_DESCRIPTION", "False"), False)
SPELL_CHECK_REPLY = is_enabled(environ.get("SPELL_CHECK_REPLY", "True"), True)
MAX_LIST_ELM = environ.get("MAX_LIST_ELM", None)
INDEX_REQ_CHANNEL = int(environ.get('INDEX_REQ_CHANNEL', LOG_CHANNEL))
FILE_STORE_CHANNEL = [int(ch) for ch in (environ.get('FILE_STORE_CHANNEL', '')).split()]
MELCOW_NEW_USERS = is_enabled((environ.get('MELCOW_NEW_USERS', "True")), True)
PROTECT_CONTENT = is_enabled((environ.get('PROTECT_CONTENT', "False")), False)
PUBLIC_FILE_STORE = is_enabled((environ.get('PUBLIC_FILE_STORE', "False")), True)

LOG_STR = "Current Cusomized Configurations are:-\n"
LOG_STR += ("IMDB Results are enabled, Bot will be showing imdb details for you queries.\n" if IMDB else "IMBD Results are disabled.\n")
LOG_STR += ("P_TTI_SHOW_OFF found , Users will be redirected to send /start to Bot PM instead of sending file file directly\n" if P_TTI_SHOW_OFF else "P_TTI_SHOW_OFF is disabled files will be send in PM, instead of sending start.\n")
LOG_STR += ("SINGLE_BUTTON is Found, filename and files size will be shown in a single button instead of two separate buttons\n" if SINGLE_BUTTON else "SINGLE_BUTTON is disabled , filename and file_sixe will be shown as different buttons\n")
LOG_STR += (f"CUSTOM_FILE_CAPTION enabled with value {CUSTOM_FILE_CAPTION}, your files will be send along with this customized caption.\n" if CUSTOM_FILE_CAPTION else "No CUSTOM_FILE_CAPTION Found, Default captions of file will be used.\n")
LOG_STR += ("Long IMDB storyline enabled." if LONG_IMDB_DESCRIPTION else "LONG_IMDB_DESCRIPTION is disabled , Plot will be shorter.\n")
LOG_STR += ("Spell Check Mode Is Enabled, bot will be suggesting related movies if movie not found\n" if SPELL_CHECK_REPLY else "SPELL_CHECK_REPLY Mode disabled\n")
LOG_STR += (f"MAX_LIST_ELM Found, long list will be shortened to first {MAX_LIST_ELM} elements\n" if MAX_LIST_ELM else "Full List of casts and crew will be shown in imdb template, restrict them by adding a value to MAX_LIST_ELM\n")
LOG_STR += f"Your current IMDB template is {IMDB_TEMPLATE}"
