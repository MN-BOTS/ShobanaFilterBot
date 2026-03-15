
<h1 align="center">
  <b>Shobana Filter Bot</b>
</h1>

<p align="center">
  A powerful and versatile Telegram bot designed for filtering, automation, and much more!
</p>
<div align="center">
  <a href="https://github.com/mn-bots/ShobanaFilterBot/stargazers">
    <img src="https://img.shields.io/github/stars/mn-bots/ShobanaFilterBot?color=black&logo=github&logoColor=black&style=for-the-badge" alt="Stars" />
  </a>
  <a href="https://github.com/mn-bots/ShobanaFilterBot/network/members">
    <img src="https://img.shields.io/github/forks/mn-bots/ShobanaFilterBot?color=black&logo=github&logoColor=black&style=for-the-badge" alt="Forks" />
  </a>
  <a href="https://github.com/mn-bots/ShobanaFilterBot">
    <img src="https://img.shields.io/github/repo-size/mn-bots/ShobanaFilterBot?color=skyblue&logo=github&logoColor=blue&style=for-the-badge" alt="Repo Size" />
  </a>
  <a href="https://github.com/mn-bots/ShobanaFilterBot/commits/main">
    <img src="https://img.shields.io/github/last-commit/mn-bots/ShobanaFilterBot?color=black&logo=github&logoColor=black&style=for-the-badge" alt="Last Commit" />
  </a>
  <a href="https://github.com/mn-bots/ShobanaFilterBot">
    <img src="https://img.shields.io/github/contributors/mn-bots/ShobanaFilterBot?color=skyblue&logo=github&logoColor=blue&style=for-the-badge" alt="Contributors" />
  </a>
  <a href="https://github.com/mn-bots/ShobanaFilterBot/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-GPL%202.0%20license-blueviolet?style=for-the-badge" alt="License" />
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Written%20in-Python-skyblue?style=for-the-badge&logo=python" alt="Python" />
  </a>
  <a href="https://pypi.org/project/Pyrogram/">
    <img src="https://img.shields.io/pypi/v/pyrogram?color=white&label=pyrogram&logo=python&logoColor=blue&style=for-the-badge" alt="Pyrogram" />
  </a>
</div>


## ✨ Features

- ✅ Auto Filter  
- ✅ Manual Filter  
- ✅ IMDB Search and Info  
- ✅ Admin Commands  
- ✅ Broadcast Messages  
- ✅ File Indexing  
- ✅ Inline Search  
- ✅ Random Pics Generator  
- ✅ User and Chat Stats  
- ✅ Ban, Unban, Enable, Disable Commands  
- ✅ File Storage  
- ✅ Auto-Approval for Requests  
- ✅ Shortener Link Support (`/short`)  
- ✅ Feedback System  
- ✅ Font Styling (`/font`)  
- ✅ User Promotion/Demotion  
- ✅ Pin/Unpin Messages  
- ✅ Image-to-Link Conversion
- ✅ Auto Delete: Automatically removes user messages after processing, so you don't need a separate auto-delete bot
- ✅ Auto Restart
- ✅ Keep Alive Function: Prevents the bot from sleeping or shutting down unexpectedly on platforms like Koyeb, eliminating the need for external uptime services like UptimeRobot.
- ✅ /movies and /series Commands: Instantly fetch and display the most recently added movies or series with these commands.
- ✅ Hyperlink Mode: When enabled, search results are sent as clickable hyperlinks instead of using callback buttons for easier access.
- ✅ Multiple Request FSub support: You can add multiple channels. Easily update the required channels with the /fsub command, e.g., /fsub (channel1 id) (channel2 id) (channel3 id).
- ✅ Delete Files by Query: Use the /deletefiles <keyword> command to delete all files containing a specific word in their name. For example, /deletefiles predvd removes all files with 'predvd' in their filename.
- ✅ Auto delete for files.
- ✅ Channel file sending mode with multiple channel support.
- ✅ SQL database (postgrasql) support (Optional).
- ✅ 5 MongoDb support (optional).



## Commands
```
start - Start the bot
movies - Latest added movies
series - Latest added series
connect - Connect group to PM
disconnect - Disconnect active chat
connections - Show your connections
settings - Open group settings
filter - Create manual filter
add - Create manual filter (alias)
filters - List filters
viewfilters - List filters (alias)
del - Delete filter
delall - Delete all filters
imdb - Search movie/series info
mnsearch - Search movie/series info (alias)
id - Show user / chat ID
info - Show user information
bug - Send bug report / feedback
bugs - Send bug report / feedback (alias)
feedback - Send feedback (alias)
search - Search from external sources
paste - Create paste link
pasty - Create paste link (alias)
tgpaste - Create paste link (alias)
short - Shorten URL
tr - Translate replied text
font - Style your text
genpassword - Generate strong password
genpw - Generate strong password (alias)
tts - Text to speech
carbon - Generate carbon image
stickerid - Get sticker file ID
json - Show message JSON
js - Show message JSON (alias)
showjson - Show message JSON (alias)
img - Upload image and get link
cup - Upload image and get link (alias)
telegraph - Upload image and get link (alias)
share - Share text as link
share_text - Share text as link (alias)
sharetext - Share text as link (alias)
echo - Repeat the text
pin - Pin replied message
unpin - Unpin a message
unpin_all - Unpin all messages
promote - Promote a user in group
demote - Demote a user in group
stats - Show bot database statistics
invite - Generate group invite link
ban - Ban user from using the bot
unban - Unban user
leave - Make bot leave a chat
disable - Disable a chat
enable - Enable a disabled chat
deletefiles - Bulk delete indexed files
deleteall - Delete all indexed files
users - List bot users
chats - List connected chats/groups
channel - List indexed channels
broadcast - Broadcast message to users
grpbroadcast - Broadcast message to groups
logs - Get recent bot logs
delete - Delete one indexed file
fsub - Update force-subscribe channels
restart - Restart the bot
ping - Check bot ping
usage - Show resource usage
set_template - Set custom template
setskip - Set skip settings
clear_join_users - Clear join users data
```

## 🔧 Variables

### Required
- `BOT_TOKEN`: Obtain via [@BotFather](https://telegram.dog/BotFather).  
- `API_ID`: Get this from [Telegram Apps](https://my.telegram.org/apps).  
- `API_HASH`: Also from [Telegram Apps](https://my.telegram.org/apps).  
- `CHANNELS`: Telegram channel/group usernames or IDs (space-separated).  
- `ADMINS`: Admin usernames or IDs (space-separated).  
- `DATABASE_URI`: Primary MongoDB URI (first priority if set).  
- `DATABASE_NAME`: Primary MongoDB database name.  
- `DATABASE_URI2`..`DATABASE_URI5`: Optional extra MongoDB URIs (up to 5 total) for sharded media indexing/search.  
- `DATABASE_NAME2`..`DATABASE_NAME5`: Optional database names for those extra MongoDB URIs (defaults to `DATABASE_NAME`).  
- `POSTGRES_URI`: PostgreSQL connection URI used when `DATABASE_URI` is not set.  
- `LOG_CHANNEL`: Telegram channel for activity logs.  

### Database priority order
1. `DATABASE_URI` (MongoDB)
2. `POSTGRES_URI` (PostgreSQL SQL backend)

### Optional
- `PICS`: Telegraph links for images in start message (space-separated).  
- `FILE_STORE_CHANNEL`: Channels for file storage (space-separated).  
- `POSTGRES_STORAGE_LIMIT_BYTES`: Optional PostgreSQL quota for accurate `/stats` free storage in SQL mode (supports formats like `1073741824`, `1024MB`, `1GB`).  
- Refer to [info.py](https://github.com/mn-bots/ShobanaFilterBot/blob/main/info.py) for more details.

---

## 🚀 Deployment (Beginner Friendly Full Guide)

This guide supports MongoDB or PostgreSQL:
1. **MongoDB** (`DATABASE_URI`) with optional media shards (`DATABASE_URI2`..`DATABASE_URI5`)
2. **PostgreSQL** (`POSTGRES_URI`) when MongoDB is not set.

---

### 1) Minimum environment variables

```env
BOT_TOKEN=123456:ABC...
API_ID=1234567
API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxx
ADMINS=123456789
CHANNELS=-1001234567890
LOG_CHANNEL=-1001234567890
```

Then choose one DB method below.

---

### 2) MongoDB connection (recommended for beginners)

1. Create account: https://www.mongodb.com/cloud/atlas/register
2. Create cluster.
3. **Database Access** → create DB user.
4. **Network Access** → allow your server IP.
5. **Connect → Drivers** → copy URI.
6. Set environment values:

```env
DATABASE_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=Cluster0
COLLECTION_NAME=mn_files
```

Quick test:
```python
from pymongo import MongoClient
uri = "mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(uri, serverSelectionTimeoutMS=5000)
print(client.admin.command("ping"))
```

---

### 3) PostgreSQL connection (exact format)

You need:
- host
- port (`5432` usually)
- database name
- username
- password

URI format:
```text
postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE_NAME
```

Example env:
```env
POSTGRES_URI=postgresql+psycopg2://bot_user:StrongPass@your-host:5432/shobana_bot
```

Create DB/user manually:
```sql
CREATE DATABASE shobana_bot;
CREATE USER bot_user WITH ENCRYPTED PASSWORD 'StrongPass';
GRANT ALL PRIVILEGES ON DATABASE shobana_bot TO bot_user;
```

Quick test:
```python
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg2://bot_user:StrongPass@your-host:5432/shobana_bot")
with engine.connect() as c:
    print(c.execute(text("SELECT 1")).scalar())
```

Important:
- Leave `DATABASE_URI` empty if using PostgreSQL.
- Set `POSTGRES_STORAGE_LIMIT_BYTES` to your provider quota (examples: `1GB`, `1024MB`, or raw bytes) if you want `/stats` free storage to show DB quota-based remaining space.
- Do not set MySQL/SQLite/Turso variables (not used in this repo now).

---

### 4) Where to deploy

- **Koyeb**: easiest for beginners
- **Render**
- **Railway**
- **VPS** (advanced)

For all platforms:
1. Fork repo.
2. Add env variables.
3. Deploy.
4. Verify bot with `/start`.

---

### 5) Common errors

1. `DATABASE_URI` set but Mongo auth fails → recheck DB username/password and network access.
2. PostgreSQL connection refused → check host/port/firewall/SSL requirements.
3. Invalid PostgreSQL URI → ensure it starts with `postgresql+psycopg2://`.
4. Bot not responding in channels → make bot admin in channels listed in `CHANNELS`.

---

💬 Support
<p> <a href="https://telegram.dog/mnbots_support" target="_blank"> <img src="https://img.shields.io/badge/Telegram-Group-30302f?style=flat&logo=telegram" alt="Telegram Group"> </a> <a href="https://telegram.dog/MrMNTG" target="_blank"> <img src="https://img.shields.io/badge/Telegram-Channel-30302f?style=flat&logo=telegram" alt="Telegram Channel"> </a> </p> <hr>
🙏 Credits
<ul> <li><a href="https://github.com/pyrogram/pyrogram" target="_blank">Dan</a> for the Pyrogram Library</li> <li><a href="https://github.com/Mahesh0253/Media-Search-bot" target="_blank">Mahesh</a> for the Media Search Bot</li> <li><a href="https://github.com/EvamariaTG/EvaMaria" target="_blank">EvamariaTG</a> for the EvaMaria Bot</li> <li><a href="https://github.com/trojanzhex/Unlimited-Filter-Bot" target="_blank">Trojanz</a> for Unlimited Filter Bot</li> <li>Goutham for ping feature</li> <li>MN TG for editing and modifying this repository(Currently It's Me)</li> <li> If your intrested to Collab with us Just fork this repo and create pull request ------<a href="https://github.com/MN-BOTS/ShobanaFilterBot/fork" target="_blank"> Click Here To Fork Repo  </a></li> </ul> <hr>
📜 Disclaimer
<p> <a href="https://www.gnu.org/licenses/agpl-3.0.en.html" target="_blank"> <img src="https://www.gnu.org/graphics/agplv3-155x51.png" alt="GNU AGPLv3"> </a> </p> <p> This project is licensed under the <a href="https://github.com/mn-bots/ShobanaFilterBot/blob/main/LICENSE" target="_blank">GNU AGPL 3.0</a>. <strong>Selling this code for monetary gain is strictly prohibited.</strong> </p> <hr> 
