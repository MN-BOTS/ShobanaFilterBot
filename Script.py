class script(object):
    START_TXT = """ Hᴇʟʟᴏ {}.
𝖨𝗆 𝖺𝗇 𝖺𝗎𝗍𝗈 𝖿𝗂𝗅𝗍𝖾𝗋 𝖻𝗈𝗍 𝗐𝗁𝗂𝖼𝗁 𝖼𝖺𝗇 𝗉𝗋𝗈𝗏𝗂𝖽𝖾 𝗆𝗈𝗏𝗂𝖾𝗌 𝗂𝗇 𝗒𝗈𝗎𝗋 𝗀𝗋𝗈𝗎𝗉𝗌.
+ 𝖠𝖽𝖽 𝖬𝖾 𝖳𝗈 𝖸𝗈𝗎𝗋 𝖦𝗋𝗈𝗎𝗉 + 𝖺𝗇𝖽 𝗉𝗋𝗈𝗆𝗈𝗍𝖾 𝗆𝖾 𝖺𝗌 𝖺𝖽𝗆𝗂𝗇 𝗍𝗈 𝗅𝖾𝗍 𝗆𝖾 𝗀𝖾𝗍 𝗂𝗇 𝖺𝖼𝗍𝗂𝗈𝗇."""
    HELP_TXT = """
<b>Hey {} 👋</b>

Use the buttons below to browse all features and commands.
Each help page contains a short list for easy reading.
"""
    HELP_PAGES = [
"""<b>📘 Help (1/6): Core Features</b>
• Auto filter and manual filter replies
• IMDB details with poster + metadata
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
• /id - Show user/chat id
• /info - Show user information
• /bug /bugs /feedback - Send feedback
• /search - Search from external sources
• /paste /pasty /tgpaste - Create paste link
• /short - Shorten URL
• /tr - Translate replied text
• /font - Style your text
• /genpassword or /genpw - Generate password""",
"""<b>📘 Help (4/6): Media/Extra Commands</b>
• /tts - Text to speech
• /carbon - Generate carbon image
• /stickerid - Get sticker file id
• /json /js /showjson - Message JSON
• /img /cup /telegraph - Image to link
• /share /share_text /sharetext - Share text
• /echo - Repeat text
• /pin - Pin replied message
• /unpin - Unpin a message
• /unpin_all - Unpin all messages""",
"""<b>📘 Help (5/6): Group/Admin Commands</b>
• /promote - Promote user in group
• /demote - Demote user in group
• /stats - Show database bot stats
• /invite - Generate group invite link
• /ban - Ban a user from bot
• /unban - Unban a user
• /leave - Leave a chat
• /disable - Disable a chat
• /enable - Enable a chat
• /deletefiles & /deleteall - Bulk file delete
• Channel send mode + auto-delete file delivery""",
"""<b>📘 Help (6/6): Owner/Admin-Only</b>
• /users - List bot users
• /chats - List connected chats
• /channel - List indexed channels
• /broadcast - Broadcast to users
• /grpbroadcast - Broadcast to groups
• /logs - Get recent logs
• /delete - Delete one indexed file
• /fsub - Update force-sub channels
• /restart, /ping, /usage - System tools
• /set_template, /setskip, /clear_join_users
• Bot commands auto-sync on startup
• Auto-update commands: /setupchat /movieupdates /getdlink /sendupnow /getlist"""
    ]
    ABOUT_TXT = """<b>
◎ Cʀᴇᴀᴛᴏʀ: <a href=https://github.com/mntgxo> MN - TG</a>
◎ Lᴀɴɢᴜᴀɢᴇ: Pʏᴛʜᴏɴ 3
◎ Dᴀᴛᴀ Bᴀsᴇ: Mᴏɴɢᴏ DB
◎ Bᴏᴛ Sᴇʀᴠᴇʀ: KoYeb</b>"""
    SOURCE_TXT = """<b>NOTE:</b>
- Shobana Filter Bot  is a open source project. 
- Source - <ahref=https://github.com/mn-bots/ShobanaFilterBot>Click Here to get source code</a>

<b>DEVS:</b>
-<a href=https://github.com/mntg4u> MN - TG</a>"""
    MANUELFILTER_TXT = """Help: <b>Filters</b>
- Filter is the feature were users can set automated replies for a particular keyword and shobana will respond whenever a keyword is found the message
<b>NOTE:</b>
1. This Bot should have admin privillage.
2. only admins can add filters in a chat.
3. alert buttons have a limit of 64 characters.

<b>Commands and Usage:</b>
• /filter - <code>add a filter in chat</code>
• /filters - <code>list all the filters of a chat</code>
• /del - <code>delete a specific filter in chat</code>
• /delall - <code>delete the whole filters in a chat (chat owner only)</code>"""
    BUTTON_TXT = """Help: <b>Buttons</b>

- This Bot Supports both url and alert inline buttons.

<b>NOTE:</b>
1. Telegram will not allows you to send buttons without any content, so content is mandatory.
2. This Bot supports buttons with any telegram media type.
3. Buttons should be properly parsed as markdown format

<b>URL buttons:</b>
<code>[Button Text](buttonurl:https://github.com/mn-bots/ShobanaFilterBot)</code>

<b>Alert buttons:</b>
<code>[Button Text](buttonalert:This is an alert message)</code>"""
    AUTOFILTER_TXT = """

<b>ɴᴏᴛᴇ: Fɪʟᴇ Iɴᴅᴇx</b>
1. ᴍᴀᴋᴇ ᴍᴇ ᴛʜᴇ ᴀᴅᴍɪɴ ᴏꜰ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ ɪꜰ ɪᴛ'ꜱ ᴘʀɪᴠᴀᴛᴇ.
2. ᴍᴀᴋᴇ ꜱᴜʀᴇ ᴛʜᴀᴛ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴅᴏᴇꜱ ɴᴏᴛ ᴄᴏɴᴛᴀɪɴꜱ ᴄᴀᴍʀɪᴘꜱ, ᴘᴏʀɴ ᴀɴᴅ ꜰᴀᴋᴇ ꜰɪʟᴇꜱ.
3. ꜰᴏʀᴡᴀʀᴅ ᴛʜᴇ ʟᴀꜱᴛ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ᴍᴇ ᴡɪᴛʜ Qᴜᴏᴛᴇꜱ. ɪ'ʟʟ ᴀᴅᴅ ᴀʟʟ ᴛʜᴇ ꜰɪʟᴇꜱ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴍʏ ᴅʙ.

<b>Nᴏᴛᴇ: AᴜᴛᴏFɪʟᴛᴇʀ</b>
1. Aᴅᴅ ᴛʜᴇ ʙᴏᴛ ᴀs ᴀᴅᴍɪɴ ᴏɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ.
2. Usᴇ /connect ᴀɴᴅ ᴄᴏɴɴᴇᴄᴛ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴛᴏ ᴛʜᴇ ʙᴏᴛ.
3. Usᴇ /settings ᴏɴ ʙᴏᴛ's PM ᴀɴᴅ ᴛᴜʀɴ ᴏɴ AᴜᴛᴏFɪʟᴛᴇʀ ᴏɴ ᴛʜᴇ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ.."""
    CONNECTION_TXT = """Help: <b>Connections</b>

- Used to connect bot to PM for managing filters 
- it helps to avoid spamming in groups.

<b>NOTE:</b>
1. Only admins can add a connection.
2. Send <code>/connect</code> for connecting me to ur PM

<b>Commands and Usage:</b>
• /connect  - <code>connect a particular chat to your PM</code>
• /disconnect  - <code>disconnect from a chat</code>
• /connections - <code>list all your connections</code>"""
    EXTRAMOD_TXT = """Help: <b>Extra Modules</b>

<b>NOTE:</b>
these are the extra features of ShobanaFilterBot

<b>Commands and Usage:</b>
• /id - <code>get id of a specified user.</code>
• /info  - <code>get information about a user.</code>
• /imdb  - <code>get the film information from IMDb source.</code>
• /search  - <code>get the film information from various sources.</code>
• /start - <code>Check I'm Alive.</code>
• /ping - <code>check ping.</code>
• /usage - <code>usage of bot.</code>
• /info - <code>User info .</code>
• /id - <code>User id  .</code>
• /broadcast - <code>Broadcast (owner only).</code>
"""
    ADMIN_TXT = """Help: <b>Admin mods</b>

<b>NOTE:</b>
This module only works for my admins

<b>Commands and Usage:</b>
• /logs - <code>to get the rescent errors</code>
• /stats - <code>to get status of files in db.</code>
• /delete - <code>to delete a specific file from db.</code>
• /users - <code>to get list of my users and ids.</code>
• /chats - <code>to get list of the my chats and ids </code>
• /leave  - <code>to leave from a chat.</code>
• /disable  -  <code>do disable a chat.</code>
• /ban  - <code>to ban a user.</code>
• /unban  - <code>to unban a user.</code>
• /channel - <code>to get list of total connected channels</code>
• /broadcast - <code>to broadcast a message to all users</code>"""
    STATUS_TXT = """★ 𝚃𝙾𝚃𝙰𝙻 𝙵𝙸𝙻𝙴𝚂: <code>{}</code>
 𝚃𝙾𝚃𝙰𝙻 𝚄𝚂𝙴𝚁𝚂: <code>{}</code>
 𝚃𝙾𝚃𝙰𝙻 𝙲𝙷𝙰𝚃𝚂: <code>{}</code>
 𝚄𝚂𝙴𝙳 𝚂𝚃𝙾𝚁𝙰𝙶𝙴: <code>{}</code> 
 𝙵𝚁𝙴𝙴 𝚂𝚃𝙾𝚁𝙰𝙶𝙴: <code>{}</code> """
    LOG_TEXT_G = """#NewGroup
Group = {}(<code>{}</code>)
Total Members = <code>{}</code>
Added By - {}
"""
    RESULT_TXT="""Hey {mention} ,     
Jᴜsᴛ Sᴇᴇ Wʜᴀᴛ I Found Fᴏʀ Yᴏᴜʀ Qᴜᴇʀʏ"""

    CUSTOM_FILE_CAPTION = """📂Fɪʟᴇɴᴀᴍᴇ : {file_name}
FɪʟᴇSɪᴢᴇ : {file_size}

╔═  ᴊᴏɪɴ ᴡɪᴛʜ ᴜs   ═╗
 Jᴏɪɴ :- [MAIN CHANNEL](https://t.me/Moviepornindia)
╚═  ᴊᴏɪɴ ᴡɪᴛʜ ᴜs    ═╝

⚠️ <b>This file will be deleted from here within 1 minute as it has copyright ... !!!</b>

"""

    
    RESTART_GC_TXT = """
<b>𝖡𝗈𝗍 𝖱𝖾𝗌𝗍𝖺𝗋𝗍𝖾𝖽 !</b>

📅 𝖣𝖺𝗍𝖾 : <code>{}</code>
⏰ 𝖳𝗂𝗆𝖾 : <code>{}</code>
🌐 𝖳𝗂𝗆𝖾𝗓𝗈𝗇𝖾 : <code>Asia/Kolkata</code>
🛠️ 𝖡𝗎𝗂𝗅𝖽 𝖲𝗍𝖺𝗍𝗎𝗌 : <code>𝗏1 [ 𝖲𝗍able ]</code></b>"""
    
    LOG_TEXT_P = """#NewUser
ID - <code>{}</code>
Name - {}
"""
    SPOLL_NOT_FND="""
I couldn't find anything related to your request. 
Try reading the instruction below 
<blockquote>
1️ Ask in Correct Spelling
2️ Don't ask Movies which are not Realased on OTT PLATFORMS
3️ Possible  ASK [movie name langauge] like this or [movie year] </blockquote>
OR
<b> Tʜɪs Mᴏᴠɪᴇ Is Nᴏᴛ Aᴅᴅᴇᴅ Tᴏ DB</b>
<pre>Report To ADMIN BY USING /bugs command </pre> 
    """
#SPELL CHECK LANGUAGES TO KNOW callback
    ENG_SPELL="""Please Note Below📓
1️⃣ Ask in Correct Spelling
2️⃣ Don't ask Movies which are not Realased on OTT PLATFORMS
3️⃣ Possible  ASK [movie name langauge] like this or [movie year]
    """
    MAL_SPELL="""ദയവായി താഴെ ശ്രദ്ധിക്കുക📓
1️⃣ ശരിയായ അക്ഷരവിന്യാസത്തിൽ ചോദിക്കുക
2️⃣ OTT പ്ലാറ്റ്‌ഫോമുകളിൽ റിലീസ് ചെയ്യാത്ത സിനിമകൾ ചോദിക്കരുത്
3️⃣ ഇത് പോലെ [സിനിമയുടെ പേര് ഭാഷ] അല്ലെങ്കിൽ [സിനിമ വർഷം] ചോദിക്കാം
    """
    HIN_SPELL="""कृपया नीचे ध्यान दें📓
1️⃣ सही वर्तनी में पूछें
2️⃣ उन फिल्मों के बारे में न पूछें जो ओटीटी प्लेटफॉर्म पर रिलीज नहीं हुई हैं
3️⃣ संभव है पूछें [मूवी का नाम भाषा] इस तरह या [मूवी वर्ष]
    """
    TAM_SPELL="""கீழே கவனிக்கவும்📓
1️⃣ சரியான எழுத்துப்பிழையில் கேளுங்கள்
2️⃣ வெளியாகாத திரைப்படங்களைக் கேட்காதீர்கள்
3️⃣ இந்த வடிவத்தில் கேளுங்கள் [திரைப்படத்தின் பெயர், ஆண்டு]
    """

    CHK_MOV_ALRT="""♻️ ᴄʜᴇᴄᴋɪɴɢ ꜰɪʟᴇ ᴏɴ ᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ... ♻️"""
    
    OLD_MES=""" 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐮𝐬𝐢𝐧𝐠 𝐨𝐧𝐞 𝐨𝐟 𝐦𝐲 𝐨𝐥𝐝 𝐦𝐞𝐬𝐬𝐚𝐠𝐞𝐬🤔, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐬𝐞𝐧𝐝 𝐭𝐡𝐞 𝐫𝐞𝐪𝐮𝐞𝐬𝐭 𝐚𝐠𝐚𝐢𝐧"""
    
    MOV_NT_FND="""<b>Tʜɪs Mᴏᴠɪᴇ Is Nᴏᴛ Yᴇᴛ Rᴇᴀʟᴇsᴇᴅ Oʀ Aᴅᴅᴇᴅ Tᴏ DB</b>
<pre>Report To ADMIN BY USING /bugs command </pre> 
"""
    RESTART_TXT = """
<b><u>𝖡𝗈𝗍 𝖱𝖾𝗌𝗍𝖺𝗋𝗍𝖾𝖽 ✅</u></b>"""
