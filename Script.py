class script(object):
    START_TXT = """Hello {}.
I am an auto-filter bot that can provide movies in your groups.
Add me to your group and promote me as admin so I can start working."""

    HELP_TXT = """
<b>Hey {} 👋</b>

Use the buttons below to browse features and commands.
Each page has a short and simple command list.
"""

    HELP_PAGES = [
"""<b>📘 Help (1/6): Core Features</b>
• Auto filter and manual filter replies
• IMDb details with poster and metadata
• Spell-check suggestions for wrong queries
• File indexing from linked channels
• Multi-database support (Mongo + SQL)
• Hyperlink result mode support
• Connection manager for PM controls
• File auto-delete and protected delivery
• Multiple force-sub channels support
• Inline search and share support""",
"""<b>📘 Help (2/6): Public Commands</b>
• /start - Start the bot
• /movies - Latest added movies
• /series - Latest added series
• /connect - Connect group to PM
• /disconnect - Disconnect active chat
• /connections - Show your connections
• /settings - Open group settings
• /filter or /add - Create manual filter
• /filters or /viewfilters - List filters
• /del and /delall - Delete filters""",
"""<b>📘 Help (3/6): Utility Commands</b>
• /imdb and /mnsearch - Search movie info
• /id - Show user/chat ID
• /info - Show user information
• /bug /bugs /feedback - Send feedback
• /search - Search from external sources
• /img /cup /telegraph - Image to link
• /share /share_text /sharetext - Share text""",
"""<b>📘 Help (4/6): Group/Admin Commands</b>
• /stats - Show database bot stats
• /invite - Generate group invite link
• /ban - Ban a user from the bot
• /unban - Unban a user
• /leave - Leave a chat
• /disable - Disable a chat
• /enable - Enable a chat
• /deletefiles and /deleteall - Bulk file delete
• Channel send mode with auto-delete""",
"""<b>📘 Help (5/6): Owner/Admin-Only</b>
• /users - List bot users
• /chats - List connected chats
• /channel - List indexed channels
• /broadcast - Broadcast to users
• /grpbroadcast - Broadcast to groups
• /logs - Get recent logs
• /delete - Delete one indexed file
• /fsub - Update force-sub channels
• /restart, /ping, /usage - System tools""",
"""<b>📘 Help (6/6): Update System</b>
• /set_template, /setskip, /clear_join_users
• /setupchat - Configure update chat IDs
• /movieupdates - Toggle auto updates
• /getdlink - Build update post
• /sendupnow - Send pending updates now
• /getlist - Get today’s added-title list
• Bot commands auto-sync on startup""",
    ]

    ABOUT_TXT = """<b>
◎ Credits: <a href=https://t.me/RHINO410Bot>t.me/RHINO410Bot</a>
◎ Language: Python 3
◎ Database: MongoDB
◎ Bot Server: Koyeb</b>"""

    SOURCE_TXT = """<b>NOTE:</b>
- Shobana Filter Bot is an open-source project.
- Source: <a href=https://github.com/mn-bots/ShobanaFilterBot>Click here to get source code</a>

<b>CREDITS:</b>
- <a href=https://t.me/RHINO410Bot>t.me/RHINO410Bot</a>"""

    MANUELFILTER_TXT = """Help: <b>Filters</b>
- Filters let users set automated replies for keywords. The bot responds when a keyword appears in a message.

<b>NOTE:</b>
1. This bot must be an admin.
2. Only admins can add filters in a chat.
3. Alert buttons have a limit of 64 characters.

<b>Commands and Usage:</b>
• /filter - <code>Add a filter in chat</code>
• /filters - <code>List all filters in a chat</code>
• /del - <code>Delete a specific filter in chat</code>
• /delall - <code>Delete all filters in a chat (chat owner only)</code>"""

    BUTTON_TXT = """Help: <b>Buttons</b>

- This bot supports both URL and alert inline buttons.

<b>NOTE:</b>
1. Telegram does not allow buttons without content.
2. This bot supports buttons with any Telegram media type.
3. Buttons should be parsed in Markdown format.

<b>URL button:</b>
<code>[Button Text](buttonurl:https://github.com/mn-bots/ShobanaFilterBot)</code>

<b>Alert button:</b>
<code>[Button Text](buttonalert:This is an alert message)</code>"""

    AUTOFILTER_TXT = """
<b>Note: File Index</b>
1. Make me an admin in your channel if it is private.
2. Make sure your channel does not contain camrips, adult content, or fake files.
3. Forward the last message to me with quotes. I will add all files from that channel to my DB.

<b>Note: AutoFilter</b>
1. Add the bot as admin in your group.
2. Use /connect and connect your group to the bot.
3. Use /settings in bot PM and turn on AutoFilter in settings."""

    CONNECTION_TXT = """Help: <b>Connections</b>

- Used to connect the bot to PM for managing filters.
- Helps avoid spam in groups.

<b>NOTE:</b>
1. Only admins can add a connection.
2. Send <code>/connect</code> to connect me to your PM.

<b>Commands and Usage:</b>
• /connect - <code>Connect a particular chat to your PM</code>
• /disconnect - <code>Disconnect from a chat</code>
• /connections - <code>List all your connections</code>"""

    EXTRAMOD_TXT = """Help: <b>Extra Modules</b>

<b>NOTE:</b>
These are the extra features of ShobanaFilterBot.

<b>Commands and Usage:</b>
• /id - <code>Get ID of a specific user</code>
• /info - <code>Get information about a user</code>
• /imdb - <code>Get film information from IMDb</code>
• /search - <code>Get film information from various sources</code>
• /start - <code>Check if I am alive</code>
• /ping - <code>Check ping</code>
• /usage - <code>Show bot usage</code>
• /broadcast - <code>Broadcast (owner only)</code>"""

    ADMIN_TXT = """Help: <b>Admin Module</b>

<b>NOTE:</b>
This module works only for admins.

<b>Commands and Usage:</b>
• /logs - <code>Get recent errors</code>
• /stats - <code>Get database status</code>
• /delete - <code>Delete a specific file from DB</code>
• /users - <code>Get list of users and IDs</code>
• /chats - <code>Get list of chats and IDs</code>
• /leave - <code>Leave a chat</code>
• /disable - <code>Disable a chat</code>
• /ban - <code>Ban a user</code>
• /unban - <code>Unban a user</code>
• /channel - <code>Get connected channels list</code>
• /broadcast - <code>Broadcast a message to all users</code>"""

    STATUS_TXT = """★ TOTAL FILES: <code>{}</code>
 TOTAL USERS: <code>{}</code>
 TOTAL CHATS: <code>{}</code>
 USED STORAGE: <code>{}</code>
 FREE STORAGE: <code>{}</code>"""

    LOG_TEXT_G = """#NewGroup
Group = {}(<code>{}</code>)
Total Members = <code>{}</code>
Added By = {}
"""

    RESULT_TXT = """Hey {mention},
Here is what I found for your query."""

    CUSTOM_FILE_CAPTION = """📂 File Name: {file_name}
📦 File Size: {file_size}

⚠️ <b>This file will be deleted from here within 3 minutes due to copyright.</b>

<b>Credits: <a href='https://t.me/RHINO410Bot'>t.me/RHINO410Bot</a></b>
"""

    RESTART_GC_TXT = """
<b>Bot Restarted!</b>

📅 Date: <code>{}</code>
⏰ Time: <code>{}</code>
🌐 Timezone: <code>Asia/Kolkata</code>
🛠️ Build Status: <code>v1 [Stable]</code>"""

    LOG_TEXT_P = """#NewUser
ID = <code>{}</code>
Name = {}
"""

    SPOLL_NOT_FND = """
I couldn't find anything related to your request.
Please check these points:
<blockquote>
1. Ask with correct spelling.
2. Do not ask for movies that are not released on OTT platforms.
3. Try this format: [movie name language] or [movie year].
</blockquote>
OR
<b>This movie is not added to the DB.</b>
<pre>Report to admin using /bugs command.</pre>
"""

    ENG_SPELL = """Please note:
1️⃣ Ask with correct spelling.
2️⃣ Do not ask for movies not released on OTT platforms.
3️⃣ Try [movie name language] or [movie year].
"""

    MAL_SPELL = """ദയവായി ശ്രദ്ധിക്കുക:
1️⃣ ശരിയായ അക്ഷരവിന്യാസത്തിൽ ചോദിക്കുക.
2️⃣ OTT പ്ലാറ്റ്‌ഫോമുകളിൽ റിലീസ് ചെയ്യാത്ത സിനിമകൾ ചോദിക്കരുത്.
3️⃣ [സിനിമയുടെ പേര് ഭാഷ] അല്ലെങ്കിൽ [സിനിമ വർഷം] എന്ന രീതിയിൽ ചോദിക്കാം.
"""

    HIN_SPELL = """कृपया ध्यान दें:
1️⃣ सही वर्तनी में पूछें।
2️⃣ ओटीटी प्लेटफॉर्म पर रिलीज न हुई फिल्मों के बारे में न पूछें।
3️⃣ [मूवी का नाम भाषा] या [मूवी वर्ष] इस तरह पूछें।
"""

    TAM_SPELL = """கீழே கவனிக்கவும்:
1️⃣ சரியான எழுத்தில் கேளுங்கள்.
2️⃣ OTT தளங்களில் வெளியாகாத படங்களை கேட்க வேண்டாம்.
3️⃣ [திரைப்படத்தின் பெயர் மொழி] அல்லது [திரைப்பட ஆண்டு] வடிவத்தில் கேளுங்கள்.
"""

    CHK_MOV_ALRT = """Checking files in my database..."""

    OLD_MES = """You are using one of my old messages. Please send your request again."""

    MOV_NT_FND = """<b>This movie is not released yet or not added to the DB.</b>
<pre>Report to admin using /bugs command.</pre>
"""

    RESTART_TXT = """
<b><u>Bot Restarted ✅</u></b>"""
