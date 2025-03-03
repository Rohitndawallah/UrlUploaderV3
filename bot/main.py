import os
import asyncio
import re
from pyrogram import Client, filters, types
from pyrogram.errors import FloodWait
from database import Database
from config import Config
from yt_helper import YTDLHelper
import datetime
from urllib.parse import urlparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot client
app = Client(
    "YTDLBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Initialize database
db = Database()
ytdl_helper = YTDLHelper()

# URL regex for YouTube-DL supported URLs
url_pattern = re.compile(r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)')

active_processes = {}
queue = asyncio.Queue()
processing = False

async def process_queue():
    global processing
    processing = True
    while not queue.empty():
        task_data = await queue.get()
        try:
            await task_data["function"](*task_data["args"])
        except Exception as e:
            logger.error(f"Error processing task: {e}")
        finally:
            queue.task_done()
    processing = False

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    
    start_msg = (
        f"👋 Hello {message.from_user.mention}!\n\n"
        f"I'm a YouTube-DL URL Uploader Bot. Send me any supported URL and I'll upload it to Telegram.\n\n"
        f"Use /settings to configure bot options.\n"
        f"Use /help to see all available commands."
    )
    
    await message.reply(
        start_msg,
        reply_markup=types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("Settings", callback_data="settings"),
             types.InlineKeyboardButton("Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "**Available Commands:**\n\n"
        "/start - Start the bot\n"
        "/settings - Configure bot settings\n"
        "/thumbnail - Set custom thumbnail (send as reply to an image)\n"
        "/delthumbnail - Delete your custom thumbnail\n"
        "/stats - View bot statistics (admin only)\n"
        "/broadcast - Broadcast message to all users (admin only)\n"
        "/ban - Ban a user (admin only)\n"
        "/unban - Unban a user (admin only)\n\n"
        "**How to use:**\n"
        "1. Send any supported URL\n"
        "2. Select desired resolution\n"
        "3. Wait for upload to complete\n\n"
        "**Features:**\n"
        "- Upload as file or video\n"
        "- Auto-split large files (>1.95GB)\n"
        "- Custom thumbnails and captions\n"
        "- Screenshot generation\n"
        "- Sample video generation"
    )
    
    await message.reply(help_text)

@app.on_message(filters.command("settings"))
async def settings_command(client, message):
    user_id = message.from_user.id
    user_settings = await db.get_user_settings(user_id)
    
    upload_mode = "Video" if user_settings["upload_as_video"] else "File"
    split_mode = "Enabled" if user_settings["split_large_files"] else "Disabled"
    screenshot_mode = "Enabled" if user_settings["generate_screenshots"] else "Disabled"
    sample_video = "Enabled" if user_settings["generate_sample"] else "Disabled"
    caption = user_settings.get("caption", "None")
    if caption and len(caption) > 15:
        caption = caption[:15] + "..."
    
    settings_msg = (
        f"**Your Settings:**\n\n"
        f"🎞 Upload Mode: {upload_mode}\n"
        f"✂️ Split Large Files: {split_mode}\n"
        f"📸 Generate Screenshots: {screenshot_mode}\n"
        f"🎬 Generate Sample Video: {sample_video}\n"
        f"📝 Caption: {caption or 'Not Set'}"
    )
    
    keyboard = [
        [types.InlineKeyboardButton(f"Upload Mode: {upload_mode}", callback_data="toggle_upload_mode")],
        [types.InlineKeyboardButton(f"Split Files: {split_mode}", callback_data="toggle_split_mode")],
        [types.InlineKeyboardButton(f"Screenshots: {screenshot_mode}", callback_data="toggle_screenshot_mode")],
        [types.InlineKeyboardButton(f"Sample Video: {sample_video}", callback_data="toggle_sample_video")],
        [types.InlineKeyboardButton("Set Caption", callback_data="set_caption"),
         types.InlineKeyboardButton("Delete Caption", callback_data="delete_caption")]
    ]
    
    await message.reply(
        settings_msg,
        reply_markup=types.InlineKeyboardMarkup(keyboard)
    )

@app.on_callback_query(filters.regex(r'^toggle_upload_mode$'))
async def toggle_upload_mode(client, callback_query):
    user_id = callback_query.from_user.id
    user_settings = await db.get_user_settings(user_id)
    new_value = not user_settings["upload_as_video"]
    await db.update_user_setting(user_id, "upload_as_video", new_value)
    mode = "Video" if new_value else "File"
    await callback_query.answer(f"Upload mode changed to {mode}")
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex(r'^toggle_split_mode$'))
async def toggle_split_mode(client, callback_query):
    user_id = callback_query.from_user.id
    user_settings = await db.get_user_settings(user_id)
    new_value = not user_settings["split_large_files"]
    await db.update_user_setting(user_id, "split_large_files", new_value)
    mode = "Enabled" if new_value else "Disabled"
    await callback_query.answer(f"Split large files: {mode}")
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex(r'^toggle_screenshot_mode$'))
async def toggle_screenshot_mode(client, callback_query):
    user_id = callback_query.from_user.id
    user_settings = await db.get_user_settings(user_id)
    new_value = not user_settings["generate_screenshots"]
    await db.update_user_setting(user_id, "generate_screenshots", new_value)
    mode = "Enabled" if new_value else "Disabled"
    await callback_query.answer(f"Screenshot generation: {mode}")
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex(r'^toggle_sample_video$'))
async def toggle_sample_video(client, callback_query):
    user_id = callback_query.from_user.id
    user_settings = await db.get_user_settings(user_id)
    new_value = not user_settings["generate_sample"]
    await db.update_user_setting(user_id, "generate_sample", new_value)
    mode = "Enabled" if new_value else "Disabled"
    await callback_query.answer(f"Sample video generation: {mode}")
    await settings_command(client, callback_query.message)

@app.on_callback_query(filters.regex(r'^set_caption$'))
async def set_caption_prompt(client, callback_query):
    await callback_query.answer("Please send your custom caption")
    
    # Create a temporary message to guide the user
    await callback_query.message.reply(
        "Please send the caption text you want to use for your uploads.\n\n"
        "Send /cancel to cancel this operation."
    )
    
    # Set user state for caption input
    await db.update_user_setting(callback_query.from_user.id, "awaiting_caption", True)

@app.on_callback_query(filters.regex(r'^delete_caption$'))
async def delete_caption(client, callback_query):
    user_id = callback_query.from_user.id
    await db.update_user_setting(user_id, "caption", None)
    await callback_query.answer("Caption deleted successfully")
    await settings_command(client, callback_query.message)

@app.on_message(filters.command("thumbnail"))
async def set_thumbnail(client, message):
    user_id = message.from_user.id
    
    if message.reply_to_message and message.reply_to_message.photo:
        # Download the photo
        photo = message.reply_to_message.photo.file_id
        download_path = f"thumbnails/{user_id}.jpg"
        
        # Ensure directory exists
        os.makedirs("thumbnails", exist_ok=True)
        
        await client.download_media(photo, file_name=download_path)
        await db.update_user_setting(user_id, "thumbnail", download_path)
        await message.reply("✅ Custom thumbnail set successfully!")
    else:
        await message.reply(
            "Please reply to an image with /thumbnail to set it as your custom thumbnail."
        )

@app.on_message(filters.command("delthumbnail"))
async def delete_thumbnail(client, message):
    user_id = message.from_user.id
    thumbnail_path = f"thumbnails/{user_id}.jpg"
    
    if os.path.exists(thumbnail_path):
        os.remove(thumbnail_path)
    
    await db.update_user_setting(user_id, "thumbnail", None)
    await message.reply("✅ Custom thumbnail deleted successfully!")

@app.on_message(filters.command("stats") & filters.user(Config.ADMIN_IDS))
async def stats_command(client, message):
    total_users = await db.get_total_users_count()
    active_today = await db.get_active_users_count(1)
    active_week = await db.get_active_users_count(7)
    total_downloads = await db.get_total_downloads()
    
    stats_text = (
        f"**Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📊 Active Users (Today): {active_today}\n"
        f"📈 Active Users (Week): {active_week}\n"
        f"📥 Total Downloads: {total_downloads}\n"
    )
    
    await message.reply(stats_text)

@app.on_message(filters.command("broadcast") & filters.user(Config.ADMIN_IDS))
async def broadcast_command(client, message):
    if not message.reply_to_message:
        await message.reply("Please reply to the message you want to broadcast.")
        return
    
    confirm_msg = await message.reply(
        "Are you sure you want to broadcast this message to all users?",
        reply_markup=types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("Yes", callback_data="confirm_broadcast"),
             types.InlineKeyboardButton("No", callback_data="cancel_broadcast")]
        ])
    )
    
    # Store message ID for future reference
    await db.update_temp_data("broadcast_msg_id", message.reply_to_message.id)
    await db.update_temp_data("broadcast_chat_id", message.chat.id)

@app.on_callback_query(filters.regex(r'^confirm_broadcast$') & filters.user(Config.ADMIN_IDS))
async def confirm_broadcast(client, callback_query):
    broadcast_msg_id = await db.get_temp_data("broadcast_msg_id")
    broadcast_chat_id = await db.get_temp_data("broadcast_chat_id")
    
    if not broadcast_msg_id:
        await callback_query.answer("Broadcast message not found.")
        return
    
    broadcast_msg = await client.get_messages(broadcast_chat_id, broadcast_msg_id)
    
    await callback_query.message.edit_text("Broadcasting message to all users...")
    
    users = await db.get_all_users()
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await broadcast_msg.copy(chat_id=user['_id'])
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send broadcast to user {user['_id']}: {e}")
        
        # Avoid FloodWait
        await asyncio.sleep(0.1)
    
    await callback_query.message.edit_text(
        f"✅ Broadcast completed!\n\n"
        f"👥 Total users: {len(users)}\n"
        f"✅ Sent successfully: {sent}\n"
        f"❌ Failed: {failed}"
    )

@app.on_callback_query(filters.regex(r'^cancel_broadcast$') & filters.user(Config.ADMIN_IDS))
async def cancel_broadcast(client, callback_query):
    await callback_query.message.edit_text("❌ Broadcast cancelled.")

@app.on_message(filters.command("ban") & filters.user(Config.ADMIN_IDS))
async def ban_user(client, message):
    if len(message.command) < 2:
        await message.reply("Please provide a user ID to ban. Usage: /ban [user_id]")
        return
    
    try:
        user_id = int(message.command[1])
        result = await db.ban_user(user_id)
        
        if result:
            await message.reply(f"✅ User {user_id} has been banned successfully.")
        else:
            await message.reply(f"❌ Failed to ban user {user_id}. User might not exist.")
    except ValueError:
        await message.reply("Please provide a valid user ID.")

@app.on_message(filters.command("unban") & filters.user(Config.ADMIN_IDS))
async def unban_user(client, message):
    if len(message.command) < 2:
        await message.reply("Please provide a user ID to unban. Usage: /unban [user_id]")
        return
    
    try:
        user_id = int(message.command[1])
        result = await db.unban_user(user_id)
        
        if result:
            await message.reply(f"✅ User {user_id} has been unbanned successfully.")
        else:
            await message.reply(f"❌ Failed to unban user {user_id}. User might not be banned.")
    except ValueError:
        await message.reply("Please provide a valid user ID.")

@app.on_message(filters.text & ~filters.command)
async def process_message(client, message):
    user_id = message.from_user.id
    user_settings = await db.get_user_settings(user_id)
    
    # Check if user is banned
    if user_settings.get("banned", False):
        await message.reply("You are banned from using this bot.")
        return
    
    # Check if user is waiting to input caption
    if user_settings.get("awaiting_caption", False):
        if message.text == "/cancel":
            await db.update_user_setting(user_id, "awaiting_caption", False)
            await message.reply("Caption setting cancelled.")
            return
            
        await db.update_user_setting(user_id, "caption", message.text)
        await db.update_user_setting(user_id, "awaiting_caption", False)
        await message.reply("✅ Caption set successfully!")
        return
    
    # Check if URL is valid
    if not url_pattern.match(message.text):
        await message.reply("Please send a valid URL.")
        return
    
    # Store URL in database
    url_id = await db.add_url(user_id, message.text)
    
    # Check if user has paid access (if paid feature is enabled)
    if Config.PAID_SERVICE and not user_settings.get("has_paid", False):
        keyboard = [[types.InlineKeyboardButton("💰 Get Premium Access", callback_data="premium_info")]]
        await message.reply(
            "⚠️ This is a premium service. Please upgrade to access download features.",
            reply_markup=types.InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Get URL info
    status_msg = await message.reply("🔍 Analyzing URL...")
    
    try:
        info = await ytdl_helper.get_info(message.text)
        
        if not info or "formats" not in info:
            await status_msg.edit_text("❌ Failed to fetch information for this URL.")
            return
        
        formats = ytdl_helper.extract_formats(info)
        
        # Create keyboard with available formats
        keyboard = []
        for i, fmt in enumerate(formats):
            if i % 2 == 0:
                keyboard.append([])
            keyboard[-1].append(
                types.InlineKeyboardButton(
                    f"{fmt['format_note']} ({fmt['ext']})",
                    callback_data=f"download_{url_id}_{fmt['format_id']}"
                )
            )
        
        # Add "Best Quality" option at the end
        keyboard.append([types.InlineKeyboardButton("✨ Best Quality", callback_data=f"download_{url_id}_best")])
        
        await status_msg.edit_text(
            f"📥 Select a format to download:\n\n"
            f"**Title:** {info.get('title', 'Unknown')}\n"
            f"**Duration:** {ytdl_helper.format_duration(info.get('duration', 0))}\n",
            reply_markup=types.InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error fetching URL info: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

@app.on_callback_query(filters.regex(r'^download_(\d+)_(.+)$'))
async def download_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_settings = await db.get_user_settings(user_id)
    
    # Check if user is banned
    if user_settings.get("banned", False):
        await callback_query.answer("You are banned from using this bot.")
        return
    
    # Extract URL ID and format ID from callback data
    match = re.match(r'^download_(\d+)_(.+)$', callback_query.data)
    if not match:
        await callback_query.answer("Invalid request.")
        return
    
    url_id, format_id = match.groups()
    url_data = await db.get_url(int(url_id))
    
    if not url_data:
        await callback_query.answer("URL not found in database.")
        return
    
    url = url_data["url"]
    
    # Check if there's already an active download for this user
    if user_id in active_processes:
        await callback_query.answer("You already have an active download. Please wait for it to complete.")
        return
    
    await callback_query.answer("Starting download...")
    
    # Update message with download status
    status_msg = await callback_query.message.edit_text(
        "⏬ Downloading...\n\n"
        "0% complete",
        reply_markup=types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("⏳ Progress", callback_data="progress_info")],
            [types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
        ])
    )
    
    # Add to download queue
    await queue.put({
        "function": process_download,
        "args": [client, user_id, url, format_id, status_msg]
    })
    
    # Start the queue processor if not already running
    if not processing:
        asyncio.create_task(process_queue())

@app.on_callback_query(filters.regex(r'^progress_info$'))
async def progress_info(client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in active_processes:
        await callback_query.answer("No active download.")
        return
    
    progress = active_processes[user_id].get("progress", 0)
    filename = active_processes[user_id].get("filename", "Unknown")
    speed = active_processes[user_id].get("speed", "Unknown")
    eta = active_processes[user_id].get("eta", "Unknown")
    
    await callback_query.answer(
        f"Progress: {progress}%\nSpeed: {speed}/s\nETA: {eta}",
        show_alert=True
    )

@app.on_callback_query(filters.regex(r'^cancel_download$'))
async def cancel_download(client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in active_processes:
        await callback_query.answer("No active download to cancel.")
        return
    
    if active_processes[user_id].get("process"):
        active_processes[user_id]["process"].terminate()
    
    active_processes.pop(user_id, None)
    await callback_query.answer("Download cancelled.")
    await callback_query.message.edit_text("❌ Download cancelled.")

async def process_download(client, user_id, url, format_id, status_msg):
    try:
        # Mark user as active
        active_processes[user_id] = {"progress": 0, "filename": "Initializing..."}
        await db.update_last_activity(user_id)
        
        # Setup progress callback
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Calculate progress
                if 'total_bytes' in d and d['total_bytes'] > 0:
                    progress = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
                else:
                    progress = 0
                
                filename = d.get('filename', 'Unknown')
                speed = d.get('_speed_str', 'Unknown')
                eta = d.get('_eta_str', 'Unknown')
                
                active_processes[user_id].update({
                    "progress": progress,
                    "filename": filename,
                    "speed": speed,
                    "eta": eta
                })
                
                # Update status message (not too frequently to avoid flood)
                if progress % 5 == 0 or progress >= 100:
                    app.loop.create_task(update_status_message(status_msg, progress, filename, speed, eta))
        
        # Get user settings
        user_settings = await db.get_user_settings(user_id)
        
        # Download the file
        await status_msg.edit_text(
            "⏬ Downloading...\n\n"
            "Preparing download...",
            reply_markup=types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("⏳ Progress", callback_data="progress_info")],
                [types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
            ])
        )
        
        download_path = await ytdl_helper.download_url(
            url,
            format_id,
            progress_hook,
            user_settings.get("split_large_files", True),
            user_settings.get("generate_sample", False)
        )
        
        if not download_path or not os.path.exists(download_path):
            raise Exception("Download failed - File not found")
        
        # Update download status
        await status_msg.edit_text(
            "✅ Download complete!\n\n"
            "🔄 Processing for upload..."
        )
        
        # Get file info
        file_size = os.path.getsize(download_path)
        filename = os.path.basename(download_path)
        
        # Check if file is too large for Telegram
        max_size = 2 * 1024 * 1024 * 1024  # 2GB (Telegram limit)
        if file_size > max_size and not user_settings.get("split_large_files", True):
            await status_msg.edit_text(
                "❌ File is too large for Telegram (>2GB).\n\n"
                "Enable 'Split Large Files' in settings to upload large files."
            )
            os.remove(download_path)
            active_processes.pop(user_id, None)
            return
        
        # Process thumbnail
        thumbnail_path = None
        if user_settings.get("thumbnail"):
            thumbnail_path = user_settings["thumbnail"]
        else:
            # Generate thumbnail from video if it's not an audio file
            if download_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv')):
                thumbnail_path = await ytdl_helper.generate_thumbnail(download_path)
        
        # Check upload mode
        upload_as_video = user_settings.get("upload_as_video", True)
        
        # Check if file needs to be split
        if file_size > 1.95 * 1024 * 1024 * 1024 and user_settings.get("split_large_files", True):
            split_files = await ytdl_helper.split_file(download_path)
            
            # Upload each part
            for i, split_path in enumerate(split_files):
                part_num = i + 1
                await status_msg.edit_text(
                    f"📤 Uploading part {part_num}/{len(split_files)}..."
                )
                
                caption = user_settings.get("caption", "")
                if caption:
                    caption = f"{caption}\n\nPart {part_num}/{len(split_files)}"
                else:
                    caption = f"Part {part_num}/{len(split_files)}"
                
                await upload_file(
                    client,
                    user_id,
                    split_path,
                    status_msg,
                    thumbnail_path,
                    caption,
                    upload_as_video
                )
                
                # Delete part after upload
                os.remove(split_path)
            
            # Generate screenshots if enabled
            if user_settings.get("generate_screenshots", False):
                screenshots = await ytdl_helper.generate_screenshots(download_path, 10)
                for screenshot in screenshots:
                    await client.send_photo(user_id, screenshot, caption="Screenshot")
                    os.remove(screenshot)
            
            await status_msg.edit_text(
                f"✅ Upload complete!\n\n"
                f"📂 All {len(split_files)} parts uploaded successfully."
            )
        else:
            # Upload as single file
            await status_msg.edit_text("📤 Uploading...")
            
            caption = user_settings.get("caption", "")
            
            await upload_file(
                client,
                user_id,
                download_path,
                status_msg,
                thumbnail_path,
                caption,
                upload_as_video
            )
            
            # Generate screenshots if enabled
            if user_settings.get("generate_screenshots", False):
                await status_msg.edit_text("🔄 Generating screenshots...")
                screenshots = await ytdl_helper.generate_screenshots(download_path, 10)
                for screenshot in screenshots:
                    await client.send_photo(user_id, screenshot, caption="Screenshot")
                    os.remove(screenshot)
            
            await status_msg.edit_text("✅ Upload complete!")
        
        # Upload sample video if enabled
        if user_settings.get("generate_sample", False) and os.path.exists(f"{download_path}.sample.mp4"):
            await client.send_video(
                user_id,
                f"{download_path}.sample.mp4",
                caption="📝 Sample Video (20 seconds)",
                thumb=thumbnail_path
            )
            os.remove(f"{download_path}.sample.mp4")
        
        # Clean up
        os.remove(download_path)
        if thumbnail_path and not thumbnail_path.startswith("thumbnails/"):
            os.remove(thumbnail_path)
        
        # Update statistics
        await db.increment_downloads()
        
    except Exception as e:
        logger.error(f"Error processing download: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
    finally:
        active_processes.pop(user_id, None)

async def upload_file(client, user_id, file_path, status_msg, thumbnail_path, caption, upload_as_video):
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    # Start the upload
    start_time = datetime.datetime.now()
    
    progress_args = (
        "📤 Uploading...\n\n"
        "{percentage}% complete\n"
        "Speed: {speed}/s\n"
        "ETA: {eta}\n\n"
        f"File: {file_name}",
        status_msg,
        start_time
    )
    
    try:
        if upload_as_video and file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv')):
            # Get video duration
            duration = await ytdl_helper.get_video_duration(file_path)
            
            # Get video width and height
            width, height = await ytdl_helper.get_video_resolution(file_path)
            
            # Upload as video
            await client.send_video(
                chat_id=user_id,
                video=file_path,
                caption=caption,
                thumb=thumbnail_path,
                duration=duration,
                width=width,
                height=height,
                supports_streaming=True,
                progress=progress_callback,
                progress_args=progress_args
            )
        else:
            # Upload as document
            await client.send_document(
                chat_id=user_id,
                document=file_path,
                caption=caption,
                thumb=thumbnail_path,
                progress=progress_callback,
                progress_args=progress_args
            )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await upload_file(client, user_id, file_path, status_msg, thumbnail_path, caption, upload_as_video)

async def progress_callback(current, total, text, message, start_time):
    try:
        if total:
            percentage = current * 100 // total
        else:
            percentage = 0
        
        elapsed_time = (datetime.datetime.now() - start_time).seconds
        
        # Calculate speed and ETA
        if elapsed_time > 0:
            #speed = current / elapsed_time
            speed = current / elapsed_time
            eta = (total - current) / speed if speed > 0 else 0
            speed_str = format_size(speed)
            eta_str = format_time(eta)
        else:
            speed_str = "N/A"
            eta_str = "N/A"
        
        # Format the progress text
        formatted_text = text.format(
            percentage=percentage,
            speed=speed_str,
            eta=eta_str
        )
        
        # Update message every 5 seconds or on 10% increments
        now = datetime.datetime.now()
        if percentage % 10 == 0 or (now - message.date).seconds >= 5:
            await message.edit_text(formatted_text)
    except Exception as e:
        logger.error(f"Error in progress callback: {e}")

def format_size(size_in_bytes):
    if size_in_bytes < 1024:
        return f"{size_in_bytes}B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes/1024:.2f}KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes/(1024*1024):.2f}MB"
    else:
        return f"{size_in_bytes/(1024*1024*1024):.2f}GB"

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60:.0f}s"
    else:
        return f"{seconds//3600}h {(seconds%3600)//60}m {seconds%3600%60:.0f}s"

async def update_status_message(message, progress, filename, speed, eta):
    try:
        await message.edit_text(
            f"⏬ Downloading...\n\n"
            f"{progress}% complete\n"
            f"Speed: {speed}/s\n"
            f"ETA: {eta}\n\n"
            f"File: {os.path.basename(filename)}",
            reply_markup=types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("⏳ Progress", callback_data="progress_info")],
                [types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
            ])
        )
    except Exception as e:
        logger.error(f"Error updating status message: {e}")

if __name__ == "__main__":
    app.run()          
          
