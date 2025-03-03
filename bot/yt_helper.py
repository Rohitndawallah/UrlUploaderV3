import os
import asyncio
import json
import re
import subprocess
import shutil
import math
from bot.config import Config
import logging

logger = logging.getLogger(__name__)

class YTDLHelper:
    def __init__(self):
        # Ensure download directory exists
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    
    async def get_info(self, url):
        """Get info about the URL using yt-dlp"""
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                url
            ]
            
            if Config.YTDL_COOKIES_FILE:
                cmd.extend(['--cookies', Config.YTDL_COOKIES_FILE])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Error getting info: {stderr.decode()}")
                return None
            
            # Parse the JSON output
            return json.loads(stdout.decode())
            
        except Exception as e:
            logger.error(f"Error getting info: {e}")
            return None
    
    def extract_formats(self, info):
        """Extract and filter available formats"""
        if not info or "formats" not in info:
            return []
        
        # Filter out formats with no filesize or audio-only formats
        formats = []
        format_ids = set()  # Keep track of unique format IDs
        
        # Sort formats by quality (height for video)
        sorted_formats = sorted(
            info["formats"],
            key=lambda x: (
                x.get("height", 0) or 0,
                x.get("tbr", 0) or 0
            ),
            reverse=True
        )
        
        for fmt in sorted_formats:
            format_id = fmt.get("format_id", "")
            
            # Skip duplicates
            if format_id in format_ids:
                continue
            
            # Skip audio-only formats
            if fmt.get("vcodec") == "none" or "audio only" in fmt.get("format", "").lower():
                continue
            
            # Get format note and extension
            format_note = fmt.get("format_note", "Unknown")
            ext = fmt.get("ext", "mp4")
            
            # Add resolution to format note if available
            height = fmt.get("height")
            if height:
                format_note = f"{height}p {format_note}"
            
            # Include format in list
            formats.append({
                "format_id": format_id,
                "format_note": format_note,
                "ext": ext,
                "filesize": fmt.get("filesize", 0)
            })
            
            format_ids.add(format_id)
            
            # Limit to top 6 formats to avoid cluttering the UI
            if len(formats) >= 6:
                break
        
        return formats
    
    def format_duration(self, seconds):
        """Format duration in seconds to HH:MM:SS format"""
        if not seconds:
            return "Unknown"
        
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    async def download_url(self, url, format_id, progress_hook, split_large=True, generate_sample=False):
        """Download the URL using yt-dlp"""
        try:
            output_template = os.path.join(Config.DOWNLOAD_DIR, "%(title)s.%(ext)s")
            
            # Base command
            cmd = [
                'yt-dlp',
                '--no-playlist',
                '--newline',
                '-o', output_template
            ]
            
            # Add format selection
            if format_id == "best":
                cmd.extend(['-f', 'best'])
            else:
                cmd.extend(['-f', format_id])
            
            # Add cookies if available
            if Config.YTDL_COOKIES_FILE:
                cmd.extend(['--cookies', Config.YTDL_COOKIES_FILE])
            
            # Add URL
            cmd.append(url)
            
            # Custom output handler
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            # Store the process to allow cancellation
            progress_hook({"status": "downloading", "downloaded_bytes": 0, "total_bytes": 100, "_speed_str": "Starting", "_eta_str": "Calculating"})
            
            # Track filename and progress
            filename = None
            total_bytes = None
            downloaded_bytes = 0
            
            async for line in process.stdout:
                line = line.decode().strip()
                
                # Extract filename
                if "[download]" in line and "Destination:" in line:
                    filename = line.split("Destination:")[1].strip()
                
                # Extract download progress
                if "[download]" in line and "%" in line:
                    try:
                        # Parse progress data
                        parts = line.split()
                        
                        # Find percentage
                        for part in parts:
                            if "%" in part:
                                percentage = float(part.rstrip("%"))
                                break
                        
                        # Find size
                        size_pattern = r"(\d+\.\d+|\d+)(Ki|Mi|Gi|Ti|B)iB?"
                        size_matches = re.findall(size_pattern, line)
                        
                        if len(size_matches) >= 2:
                            # The format is usually "downloaded / total"
                            downloaded_size, downloaded_unit = size_matches[0]
                            total_size, total_unit = size_matches[1]
                            
                            # Convert to bytes
                            unit_multiplier = {
                                "B": 1,
                                "Ki": 1024,
                                "Mi": 1024 * 1024,
                                "Gi": 1024 * 1024 * 1024,
                                "Ti": 1024 * 1024 * 1024 * 1024
                            }
                            
                            downloaded_bytes = float(downloaded_size) * unit_multiplier.get(downloaded_unit, 1)
                            total_bytes = float(total_size) * unit_multiplier.get(total_unit, 1)
                        
                        # Find speed
                        speed_pattern = r"at\s+(\d+\.\d+|\d+)(Ki|Mi|Gi|Ti|B)iB/s"
                        speed_match = re.search(speed_pattern, line)
                        if speed_match:
                            speed_value, speed_unit = speed_match.groups()
                            speed_str = f"{speed_value} {speed_unit}B/s"
                        else:
                            speed_str = "Unknown"
                        
                        # Find ETA
                        eta_pattern = r"ETA\s+(\d+:)?\d+:\d+"
                        eta_match = re.search(eta_pattern, line)
                        if eta_match:
                            eta_str = eta_match.group().replace("ETA ", "")
                        else:
                            eta_str = "Unknown"
                        
                        # Update progress
                        progress_hook({
                            "status": "downloading",
                            "downloaded_bytes": downloaded_bytes,
                            "total_bytes": total_bytes,
                            "filename": filename,
                            "_speed_str": speed_str,
                            "_eta_str": eta_str
                        })
                    except Exception as e:
                        logger.error(f"Error parsing progress: {e}")
            
            await process.wait()
            
            if process.returncode != 0:
                logger.error(f"Download failed with return code {process.returncode}")
                return None
            
            if not filename or not os.path.exists(filename):
                logger.error(f"Downloaded file not found: {filename}")
                return None
            
            # Generate a 20-second sample if requested
            if generate_sample and filename.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv')):
                await self.generate_sample_video(filename)
            
            return filename
        
        except Exception as e:
            logger.error(f"Error downloading: {e}")
            return None
    
    async def split_file(self, file_path, chunk_size=1.95*1024*1024*1024):
        """Split a large file into smaller chunks"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size <= chunk_size:
                return [file_path]
            
            # Calculate number of parts
            num_parts = math.ceil(file_size / chunk_size)
            
            base_name = os.path.splitext(file_path)[0]
            ext = os.path.splitext(file_path)[1]
            
            chunk_files = []
            
            # Use FFmpeg for video files to preserve seeking ability
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv')):
                # Get video duration
                duration = await self.get_video_duration(file_path)
                if duration:
                    part_duration = duration / num_parts
                    
                    for i in range(num_parts):
                        start_time = i * part_duration
                        output_file = f"{base_name}.part{i+1:03d}{ext}"
                        
                        cmd = [
                            'ffmpeg',
                            '-i', file_path,
                            '-ss', str(start_time),
                            '-t', str(part_duration),
                            '-c', 'copy',
                            output_file
                        ]
                        
                        process = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        
                        await process.wait()
                        
                        if os.path.exists(output_file):
                            chunk_files.append(output_file)
                
                return chunk_files
            else:
                # Use standard binary split for non-video files
                bytes_per_chunk = int(chunk_size)
                
                with open(file_path, 'rb') as f:
                    for i in range(num_parts):
                        chunk_file = f"{base_name}.part{i+1:03d}{ext}"
                        with open(chunk_file, 'wb') as chunk:
                            data = f.read(bytes_per_chunk)
                            if data:
                                chunk.write(data)
                                chunk_files.append(chunk_file)
                
                return chunk_files
                
        except Exception as e:
            logger.error(f"Error splitting file: {e}")
            return [file_path]
    
    async def generate_thumbnail(self, video_path):
        """Generate a thumbnail from a video file"""
        try:
            thumbnail_path = f"{os.path.splitext(video_path)[0]}.jpg"
            
            # Extract a frame at 20% of the video
            duration = await self.get_video_duration(video_path)
            if duration:
                position = min(duration * 0.2, 10)  # 20% or 10 seconds, whichever is less
                
                cmd = [
                    'ffmpeg',
                    '-i', video_path,
                    '-ss', str(position),
                    '-vframes', '1',
                    '-vf', 'scale=320:180',
                    thumbnail_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                await process.wait()
                
                if os.path.exists(thumbnail_path):
                    return thumbnail_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return None
    
    async def generate_screenshots(self, video_path, count=10):
        """Generate multiple screenshots from a video file"""
        try:
            screenshots = []
            duration = await self.get_video_duration(video_path)
            
            if not duration:
                return screenshots
            
            # Calculate screenshot positions
            interval = duration / (count + 1)
            positions = [interval * (i + 1) for i in range(count)]
            
            # Create output directory
            screenshots_dir = f"{os.path.splitext(video_path)[0]}_screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            
            # Generate screenshots
            for i, position in enumerate(positions):
                screenshot_path = os.path.join(screenshots_dir, f"screenshot_{i+1:02d}.jpg")
                
                cmd = [
                    'ffmpeg',
                    '-i', video_path,
                    '-ss', str(position),
                    '-vframes', '1',
                    '-vf', 'scale=640:360',
                    screenshot_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                await process.wait()
                
                if os.path.exists(screenshot_path):
                    screenshots.append(screenshot_path)
            
            return screenshots
            
        except Exception as e:
            logger.error(f"Error generating screenshots: {e}")
            return []
    
    async def generate_sample_video(self, video_path, duration=20):
        """Generate a short sample video"""
        try:
            sample_path = f"{video_path}.sample.mp4"
            
            # Get video duration
            full_duration = await self.get_video_duration(video_path)
            if not full_duration:
                return None
            
            # Start from 20% of the video
            start_position = min(full_duration * 0.2, 30)
            
            # Generate sample video
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(start_position),
                '-t', str(duration),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:v', '1M',
                '-b:a', '128k',
                sample_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.wait()
            
            if os.path.exists(sample_path):
                return sample_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating sample video: {e}")
            return None
    
    async def get_video_duration(self, video_path):
        """Get the duration of a video file in seconds"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return None
            
            data = json.loads(stdout.decode())
            return float(data.get('format', {}).get('duration', 0))
            
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return None
    
    async def get_video_resolution(self, video_path):
        """Get the width and height of a video file"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'json',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return 0, 0
            
            data = json.loads(stdout.decode())
            
            if 'streams' in data and data['streams']:
                width = int(data['streams'][0].get('width', 0))
                height = int(data['streams'][0].get('height', 0))
                return width, height
            
            return 0, 0
            
        except Exception as e:
            logger.error(f"Error getting video resolution: {e}")
            return 0, 0
