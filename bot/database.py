import motor.motor_asyncio
from config import Config
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        # Connect to MongoDB
        self.client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGODB_URI)
        self.db = self.client[Config.DATABASE_NAME]
        self.users = self.db.users
        self.urls = self.db.urls
        self.temp = self.db.temp_data
    
    async def add_user(self, user_id):
        """Add a new user or update existing user's last activity"""
        user = await self.users.find_one({"_id": user_id})
        
        if user:
            # Update last activity
            await self.users.update_one(
                {"_id": user_id},
                {"$set": {"last_activity": datetime.now()}}
            )
            return False
        else:
            # Add new user with default settings
            user_data = {
                "_id": user_id,
                "joined_date": datetime.now(),
                "last_activity": datetime.now(),
                "banned": False,
                "has_paid": False,
                "settings": {
                    "upload_as_video": True,
                    "split_large_files": True,
                    "generate_screenshots": False,
                    "generate_sample": False,
                    "caption": None,
                    "thumbnail": None
                }
            }
            
            await self.users.insert_one(user_data)
            return True
    
    async def get_user_settings(self, user_id):
        """Get user settings or create default if user doesn't exist"""
        user = await self.users.find_one({"_id": user_id})
        
        if not user:
            await self.add_user(user_id)
            user = await self.users.find_one({"_id": user_id})
        
        settings = user.get("settings", {})
        settings.update({
            "banned": user.get("banned", False),
            "has_paid": user.get("has_paid", False),
            "awaiting_caption": user.get("awaiting_caption", False)
        })
        
        return settings
    
    async def update_user_setting(self, user_id, key, value):
        """Update a specific user setting"""
        if key in ["banned", "has_paid", "awaiting_caption"]:
            # These are direct fields in the user document
            return await self.users.update_one(
                {"_id": user_id},
                {"$set": {key: value}}
            )
        else:
            # These are nested inside the settings object
            return await self.users.update_one(
                {"_id": user_id},
                {"$set": {f"settings.{key}": value}}
            )
    
    async def update_last_activity(self, user_id):
        """Update user's last activity timestamp"""
        return await self.users.update_one(
            {"_id": user_id},
            {"$set": {"last_activity": datetime.now()}}
        )
    
    async def ban_user(self, user_id):
        """Ban a user from using the bot"""
        user = await self.users.find_one({"_id": user_id})
        if not user:
            return False
        
        result = await self.users.update_one(
            {"_id": user_id},
            {"$set": {"banned": True}}
        )
        
        return result.modified_count > 0
    
    async def unban_user(self, user_id):
        """Unban a previously banned user"""
        user = await self.users.find_one({"_id": user_id})
        if not user or not user.get("banned", False):
            return False
        
        result = await self.users.update_one(
            {"_id": user_id},
            {"$set": {"banned": False}}
        )
        
        return result.modified_count > 0
    
    async def add_url(self, user_id, url):
        """Add a URL to the database and return the URL ID"""
        url_data = {
            "user_id": user_id,
            "url": url,
            "timestamp": datetime.now()
        }
        
        result = await self.urls.insert_one(url_data)
        return result.inserted_id
    
    async def get_url(self, url_id):
        """Get URL data by ID"""
        return await self.urls.find_one({"_id": url_id})
    
    async def get_total_users_count(self):
        """Get the total number of users"""
        return await self.users.count_documents({})
    
    async def get_active_users_count(self, days=1):
        """Get the number of active users in the last X days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return await self.users.count_documents({
            "last_activity": {"$gte": cutoff_date}
        })
    
    async def get_all_users(self):
        """Get all users from the database"""
        return await self.users.find({}).to_list(length=None)
    
    async def increment_downloads(self):
        """Increment the download counter"""
        stats = await self.db.stats.find_one({"_id": "downloads"})
        
        if stats:
            await self.db.stats.update_one(
                {"_id": "downloads"},
                {"$inc": {"count": 1}}
            )
        else:
            await self.db.stats.insert_one({
                "_id": "downloads",
                "count": 1
            })
    
    async def get_total_downloads(self):
        """Get the total number of downloads"""
        stats = await self.db.stats.find_one({"_id": "downloads"})
        return stats.get("count", 0) if stats else 0
    
    async def update_temp_data(self, key, value):
        """Store temporary data"""
        await self.temp.update_one(
            {"_id": key},
            {"$set": {"value": value}},
            upsert=True
        )
    
    async def get_temp_data(self, key):
        """Retrieve temporary data"""
        data = await self.temp.find_one({"_id": key})
        return data.get("value") if data else None
