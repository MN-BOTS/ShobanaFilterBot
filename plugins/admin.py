import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS
from database.users_chats_db import db
import plugins.new_updates as nu
from plugins.commands import build_fsub_details_text


def is_admin(user) -> bool:
    return user and (user.id in ADMINS or (f"@{user.username}" in ADMINS if user.username else False))


def _updates_text():
    cfg = nu.get_runtime_update_config()
    return (
        "<b>Movie Updates Config</b>\n\n"
        f"PAGE_SIZE: <code>{cfg['PAGE_SIZE']}</code>\n"
        f"SEND_DELAY: <code>{cfg['SEND_DELAY']}</code>\n"
        f"GETDLINK_PAGE_SIZE: <code>{cfg['GETDLINK_PAGE_SIZE']}</code>\n"
        f"GROUP_SIZE: <code>{cfg['GROUP_SIZE']}</code>\n"
        f"CHANNEL_SEND_MODE: <code>{cfg['CHANNEL_SEND_MODE']}</code>\n"
        f"GROUP_SEARCH_TEXT: <code>{cfg['GROUP_SEARCH_TEXT']}</code>"
    )


def _updates_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Movie Channels", callback_data="admin:upd:channels"), InlineKeyboardButton("Set New Chat", callback_data="admin:upd:setchat")],
        [InlineKeyboardButton("Mode", callback_data="admin:upd:mode"), InlineKeyboardButton("Group Size", callback_data="admin:upd:gsize")],
        [InlineKeyboardButton("Page Size", callback_data="admin:upd:psize"), InlineKeyboardButton("Send Delay", callback_data="admin:upd:sdelay")],
        [InlineKeyboardButton("GetDLink Size", callback_data="admin:upd:dlsize"), InlineKeyboardButton("Refresh", callback_data="admin:updates")],
        [InlineKeyboardButton("Back", callback_data="admin:back")],
    ])


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
    text = await build_fsub_details_text(client)
    await query.message.edit_text(text, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^admin:updates$"))
async def admin_updates(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    await query.message.edit_text(_updates_text(), reply_markup=_updates_markup())


@Client.on_callback_query(filters.regex(r"^admin:back$"))
async def admin_back(client, query):
    if not is_admin(query.from_user):
        return await query.answer("Not allowed", show_alert=True)
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("FSUB", callback_data="admin:fsub")],
        [InlineKeyboardButton("Movie Updates", callback_data="admin:updates")],
    ])
    await query.message.edit_text("⚙️ <b>Admin Panel</b>\nChoose a section:", reply_markup=buttons)


@Client.on_callback_query(filters.regex(r"^admin:upd:channels$"))
async def admin_upd_channels(client, query):
    ids = await db.get_update_chat_ids()
    if not ids:
        return await query.answer("No update chats set", show_alert=True)
    lines = ["<b>Update Chats</b>"]
    for cid in ids:
        try:
            c = await client.get_chat(int(cid))
            name = c.title or c.first_name or "Unknown"
            lines.append(f"\n• {name} - <code>{cid}</code>")
        except Exception:
            lines.append(f"\n• <code>{cid}</code>")
    await query.message.edit_text("\n".join(lines), reply_markup=_updates_markup())

@Client.on_callback_query(filters.regex(r"^admin:upd:setchat$"))
async def admin_upd_setchat(client, query):
    await query.message.reply("Use: <code>/setupchat -100123 -100456</code>")
    await query.answer()

@Client.on_callback_query(filters.regex(r"^admin:upd:mode$"))
async def admin_upd_mode(client, query):
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("individual", callback_data="admin:setmode:individual"), InlineKeyboardButton("grouped", callback_data="admin:setmode:grouped"), InlineKeyboardButton("manual", callback_data="admin:setmode:manual")],[InlineKeyboardButton("Back", callback_data="admin:updates")]])
    await query.message.edit_text("Choose CHANNEL_SEND_MODE:", reply_markup=kb)

@Client.on_callback_query(filters.regex(r"^admin:setmode:(individual|grouped|manual)$"))
async def admin_setmode(client, query):
    mode = query.matches[0].group(1)
    nu.set_runtime_update_config("CHANNEL_SEND_MODE", mode)
    await query.answer(f"Mode set to {mode}")
    await query.message.edit_text(_updates_text(), reply_markup=_updates_markup())

@Client.on_callback_query(filters.regex(r"^admin:upd:(gsize|psize|dlsize|sdelay)$"))
async def admin_upd_numeric(client, query):
    key=query.matches[0].group(1)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("-", callback_data=f"admin:num:{key}:-1"), InlineKeyboardButton("+", callback_data=f"admin:num:{key}:1")],[InlineKeyboardButton("Back", callback_data="admin:updates")]])
    await query.message.edit_text(f"Adjust {key}", reply_markup=kb)

@Client.on_callback_query(filters.regex(r"^admin:num:(gsize|psize|dlsize|sdelay):(-?1)$"))
async def admin_num_apply(client, query):
    key,delta=query.matches[0].group(1), int(query.matches[0].group(2))
    cfg = nu.get_runtime_update_config()
    if key=="gsize": nu.set_runtime_update_config("GROUP_SIZE", cfg["GROUP_SIZE"] + delta)
    elif key=="psize": nu.set_runtime_update_config("PAGE_SIZE", cfg["PAGE_SIZE"] + delta)
    elif key=="dlsize": nu.set_runtime_update_config("GETDLINK_PAGE_SIZE", cfg["GETDLINK_PAGE_SIZE"] + delta)
    elif key=="sdelay": nu.set_runtime_update_config("SEND_DELAY", round(cfg["SEND_DELAY"] + (0.1*delta), 2))
    await query.answer("Updated")
    await query.message.edit_text(_updates_text(), reply_markup=_updates_markup())
