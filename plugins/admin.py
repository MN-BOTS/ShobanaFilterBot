import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS
from database.users_chats_db import db


def is_admin(user) -> bool:
    return user and (user.id in ADMINS or (f"@{user.username}" in ADMINS if user.username else False))


@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user):
        return await message.reply("🚫 You are not authorized.")
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("FSUB", callback_data="admin:fsub")],
        [InlineKeyboardButton("Movie Updates", callback_data="admin:updates")],
    ])
    await message.reply("⚙️ <b>Admin Panel</b>\nChoose a section:", reply_markup=buttons)


@Client.on_callback_query(filters.regex(r"^admin:fsub$"))
async def admin_fsub_menu(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set New Chats", callback_data="admin:fsub:set")],
        [InlineKeyboardButton("Show Current FSUB", callback_data="admin:fsub:show")],
        [InlineKeyboardButton("Back", callback_data="admin:back")],
    ])
    await query.message.edit_text("FSUB options:", reply_markup=buttons)


@Client.on_callback_query(filters.regex(r"^admin:fsub:set$"))
async def admin_fsub_set(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    await query.answer()
    await query.message.reply("Use:\n<code>/fsub -100123 -100456 ...</code>")


@Client.on_callback_query(filters.regex(r"^admin:fsub:show$"))
async def admin_fsub_show(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    channels = await db.get_auth_channels()
    if not channels:
        return await query.message.edit_text("No FSUB chats configured.")

    lines = ["<b>Current FSUB Chats</b>"]
    for cid in channels:
        try:
            chat = await client.get_chat(int(cid))
            title = chat.title or chat.first_name or "Unknown"
            if chat.username:
                link = f"https://t.me/{chat.username}"
            else:
                invite = await client.create_chat_invite_link(int(cid), member_limit=1)
                link = invite.invite_link
            lines.append(f"\n• <b>{title}</b>\nID: <code>{cid}</code>\nLink: {link}")
            await asyncio.sleep(0.2)
        except Exception:
            lines.append(f"\n• ID: <code>{cid}</code>\nLink: unavailable")

    await query.message.edit_text("\n".join(lines), disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^admin:updates$"))
async def admin_updates(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    text = (
        "<b>Movie Updates Config</b>\n\n"
        "• <code>/setupchat</code> - set/list update channels\n"
        "• <code>/movieupdates on|off</code> - enable/disable auto updates\n"
        "• <code>/getdlink</code> - build & preview one update post\n"
        "• <code>/sendupnow</code> - flush pending grouped updates\n"
        "• <code>/latest</code> - view today's latest list"
    )
    await query.message.edit_text(text)


@Client.on_callback_query(filters.regex(r"^admin:back$"))
async def admin_back(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("FSUB", callback_data="admin:fsub")],
        [InlineKeyboardButton("Movie Updates", callback_data="admin:updates")],
    ])
    await query.message.edit_text("⚙️ <b>Admin Panel</b>\nChoose a section:", reply_markup=buttons)
