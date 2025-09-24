#!/usr/bin/env python3
"""
Jellyfin Library Monitor
Monitors filesystem changes in Jellyfin library folders and triggers automatic library refreshes.
"""

import os
import sys
import time
import json
import logging
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Dict, List, Set
import argparse
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jellyfin_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class JellyfinAPI:
    """Handle Jellyfin API interactions"""
    
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'X-Emby-Token': api_key,
            'Content-Type': 'application/json'
        })
    
    def get_libraries(self) -> Dict[str, Dict]:
        """Get all libraries from Jellyfin"""
        try:
            response = self.session.get(f"{self.server_url}/Library/VirtualFolders")
            response.raise_for_status()
            libraries = {}
            
            for lib in response.json():
                lib_id = lib['ItemId']
                lib_name = lib['Name']
                lib_paths = lib.get('Locations', [])
                libraries[lib_id] = {
                    'name': lib_name,
                    'paths': lib_paths,
                    'type': lib.get('CollectionType', 'mixed')
                }
            
            logger.info(f"Found {len(libraries)} libraries")
            return libraries
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get libraries: {e}")
            return {}
    
    def refresh_library(self, library_id: str) -> bool:
        """Trigger a library refresh"""
        try:
            url = f"{self.server_url}/Library/Refresh"
            params = {'Ids': library_id}
            
            response = self.session.post(url, params=params)
            response.raise_for_status()
            
            logger.info(f"Successfully triggered refresh for library {library_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh library {library_id}: {e}")
            return False

class LibraryChangeHandler(FileSystemEventHandler):
    """Handle filesystem events for library folders"""
    
    def __init__(self, jellyfin_api: JellyfinAPI, path_to_library: Dict[str, str], 
                 debounce_seconds: int = 30):
        self.jellyfin_api = jellyfin_api
        self.path_to_library = path_to_library
        self.debounce_seconds = debounce_seconds
        self.pending_refreshes: Dict[str, datetime] = {}
        
        # File extensions to monitor (add more as needed)
        self.monitored_extensions = {
            '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma', '.m4a',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',
            '.nfo', '.xml', '.srt', '.ass', '.ssa', '.vtt', '.sub'
        }
    
    def should_monitor_file(self, file_path: str) -> bool:
        """Check if file should trigger a library refresh"""
        if not file_path:
            return False
            
        # Check file extension
        ext = Path(file_path).suffix.lower()
        if ext not in self.monitored_extensions:
            return False
        
        # Ignore temporary files
        filename = Path(file_path).name
        if filename.startswith('.') or filename.startswith('~'):
            return False
        
        # Ignore partial downloads
        if '.part' in filename or '.tmp' in filename:
            return False
            
        return True
    
    def get_library_for_path(self, file_path: str) -> str:
        """Find which library a file path belongs to"""
        abs_path = os.path.abspath(file_path)
        
        # Find the most specific library path that contains this file
        best_match = ""
        best_library = ""
        
        for lib_path, lib_id in self.path_to_library.items():
            abs_lib_path = os.path.abspath(lib_path)
            if abs_path.startswith(abs_lib_path):
                if len(abs_lib_path) > len(best_match):
                    best_match = abs_lib_path
                    best_library = lib_id
        
        return best_library
    
    def schedule_refresh(self, library_id: str, library_name: str):
        """Schedule a library refresh with debouncing"""
        if not library_id:
            return
        
        now = datetime.now()
        self.pending_refreshes[library_id] = now + timedelta(seconds=self.debounce_seconds)
        
        logger.info(f"Scheduled refresh for library '{library_name}' (ID: {library_id}) "
                   f"in {self.debounce_seconds} seconds")
    
    def process_pending_refreshes(self):
        """Process any pending library refreshes"""
        now = datetime.now()
        completed_refreshes = []
        
        for library_id, refresh_time in self.pending_refreshes.items():
            if now >= refresh_time:
                if self.jellyfin_api.refresh_library(library_id):
                    completed_refreshes.append(library_id)
                else:
                    # Retry in 60 seconds on failure
                    self.pending_refreshes[library_id] = now + timedelta(seconds=60)
        
        # Remove completed refreshes
        for library_id in completed_refreshes:
            del self.pending_refreshes[library_id]
    
    def on_created(self, event):
        if not event.is_directory and self.should_monitor_file(event.src_path):
            library_id = self.get_library_for_path(event.src_path)
            if library_id:
                logger.info(f"File created: {event.src_path}")
                self.schedule_refresh(library_id, "Library")
    
    def on_deleted(self, event):
        if not event.is_directory and self.should_monitor_file(event.src_path):
            library_id = self.get_library_for_path(event.src_path)
            if library_id:
                logger.info(f"File deleted: {event.src_path}")
                self.schedule_refresh(library_id, "Library")
    
    def on_moved(self, event):
        if not event.is_directory:
            # Check both source and destination paths
            for path in [event.src_path, event.dest_path]:
                if self.should_monitor_file(path):
                    library_id = self.get_library_for_path(path)
                    if library_id:
                        logger.info(f"File moved: {event.src_path} -> {event.dest_path}")
                        self.schedule_refresh(library_id, "Library")
                        break

class JellyfinMonitor:
    """Main monitor class"""
    
    def __init__(self, config_file: str = None):
        self.config = self.load_config(config_file)
        self.jellyfin_api = JellyfinAPI(
            self.config['jellyfin']['server_url'],
            self.config['jellyfin']['api_key']
        )
        self.observer = Observer()
        self.handler = None
    
    def load_config(self, config_file: str = None) -> Dict:
        """Load configuration from file or use defaults"""
        default_config = {
            "jellyfin": {
                "server_url": "http://localhost:8096",
                "api_key": ""
            },
            "monitoring": {
                "debounce_seconds": 30,
                "recursive": True
            }
        }
        
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                    # Merge with defaults
                    for section, settings in user_config.items():
                        if section in default_config:
                            default_config[section].update(settings)
                        else:
                            default_config[section] = settings
            except Exception as e:
                logger.error(f"Failed to load config file: {e}")
        
        return default_config
    
    def save_sample_config(self, filename: str = "jellyfin_monitor_config.json"):
        """Save a sample configuration file"""
        sample_config = {
            "jellyfin": {
                "server_url": "http://localhost:8096",
                "api_key": "YOUR_JELLYFIN_API_KEY_HERE"
            },
            "monitoring": {
                "debounce_seconds": 30,
                "recursive": True
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(sample_config, f, indent=2)
        
        logger.info(f"Sample config saved to {filename}")
    
    def setup_monitoring(self) -> bool:
        """Setup filesystem monitoring for all library paths"""
        if not self.config['jellyfin']['api_key']:
            logger.error("Jellyfin API key not configured!")
            return False
        
        # Get libraries from Jellyfin
        libraries = self.jellyfin_api.get_libraries()
        if not libraries:
            logger.error("No libraries found or failed to connect to Jellyfin")
            return False
        
        # Build path to library mapping
        path_to_library = {}
        monitored_paths = set()
        
        for lib_id, lib_info in libraries.items():
            logger.info(f"Library: {lib_info['name']} ({lib_info['type']})")
            for path in lib_info['paths']:
                if os.path.exists(path):
                    path_to_library[path] = lib_id
                    monitored_paths.add(path)
                    logger.info(f"  Monitoring: {path}")
                else:
                    logger.warning(f"  Path not found: {path}")
        
        if not monitored_paths:
            logger.error("No valid library paths found to monitor")
            return False
        
        # Create event handler
        self.handler = LibraryChangeHandler(
            self.jellyfin_api,
            path_to_library,
            self.config['monitoring']['debounce_seconds']
        )
        
        # Add watchers for each path
        for path in monitored_paths:
            self.observer.schedule(
                self.handler,
                path,
                recursive=self.config['monitoring']['recursive']
            )
        
        return True
    
    def run(self):
        """Start monitoring"""
        if not self.setup_monitoring():
            return
        
        logger.info("Starting Jellyfin library monitor...")
        self.observer.start()
        
        try:
            while True:
                time.sleep(5)
                # Process any pending refreshes
                if self.handler:
                    self.handler.process_pending_refreshes()
                    
        except KeyboardInterrupt:
            logger.info("Stopping monitor...")
            self.observer.stop()
        
        self.observer.join()
        logger.info("Monitor stopped")

def main():
    parser = argparse.ArgumentParser(description="Monitor Jellyfin library folders and auto-refresh")
    parser.add_argument('--config', '-c', help='Configuration file path')
    parser.add_argument('--generate-config', action='store_true', 
                       help='Generate sample configuration file')
    
    args = parser.parse_args()
    
    if args.generate_config:
        monitor = JellyfinMonitor()
        monitor.save_sample_config()
        return
    
    monitor = JellyfinMonitor(args.config)
    monitor.run()

if __name__ == "__main__":
    main()
