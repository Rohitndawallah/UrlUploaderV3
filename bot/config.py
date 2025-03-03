import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    # Bot API credentials
    API_ID = int(os.environ.get("API_ID", "12345"))
    API_HASH = os.environ.get("API_HASH", "your_api_hash")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
    
    # MongoDB settings
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "ytdl_bot")
    
    # Admin settings
    ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "123456789").split(",")]
    
    # Download settings
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
    MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))  # 2GB default
    
    # Premium service settings
    PAID_SERVICE = os.environ.get("PAID_SERVICE", "False").lower() == "true"
    
    # YTDL settings
    YTDL_COOKIES_FILE = os.environ.get("YTDL_COOKIES_FILE", None)
    YTDL_MAX_FILESIZE = int(os.environ.get("YTDL_MAX_FILESIZE", str(5 * 1024 * 1024 * 1024)))  # 5GB default
