"""
Sync Config Migration Script for DriveMapper Pro v5.6+
Adds missing fields to existing sync profile configurations
"""
import json
import os
import shutil

SYNC_CONFIG_FILE = "sync_profiles.json"
BACKUP_FILE = "sync_profiles_backup.json"

def migrate_sync_config():
    if not os.path.exists(SYNC_CONFIG_FILE):
        print("No sync config file found. Nothing to migrate.")
        print("This is normal if you haven't created any sync profiles yet.")
        return
    
    # Backup original config
    shutil.copy(SYNC_CONFIG_FILE, BACKUP_FILE)
    print(f"✓ Backed up sync config to {BACKUP_FILE}")
    
    # Load config
    try:
        with open(SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        return
    
    if not isinstance(config, list):
        print("✗ Invalid config format. Aborting.")
        return
    
    # Migrate each sync profile
    modified = False
    for profile in config:
        # Add missing 'tool' field
        if 'tool' not in profile:
            profile['tool'] = 'rclone'
            modified = True
            print(f"  Added 'tool' field to profile: {profile.get('name', 'Unnamed')}")
        
        # Add missing 'mode' field
        if 'mode' not in profile:
            profile['mode'] = 'Bidirectional Sync'
            modified = True
            print(f"  Added 'mode' field to profile: {profile.get('name', 'Unnamed')}")
        
        # Add missing 'name' field
        if 'name' not in profile:
            profile['name'] = f"Sync_{profile.get('source', 'source')}_to_{profile.get('dest', 'dest')}"
            modified = True
            print(f"  Added 'name' field to profile")
        
        # Add missing 'source' field
        if 'source' not in profile:
            profile['source'] = ''
            modified = True
            print(f"  Added empty 'source' field")
        
        # Add missing 'dest' field
        if 'dest' not in profile:
            profile['dest'] = ''
            modified = True
            print(f"  Added empty 'dest' field")
        
        # Add missing 'schedule' field
        if 'schedule' not in profile:
            profile['schedule'] = 'Manual'
            modified = True
            print(f"  Added 'schedule' field")
        
        # Add missing 'last_sync' field
        if 'last_sync' not in profile:
            profile['last_sync'] = 'Never'
            modified = True
            print(f"  Added 'last_sync' field")
    
    if modified:
        # Save updated config
        try:
            with open(SYNC_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
            print(f"\n✓ Migrated {len(config)} sync profile(s)")
            print("✓ Migration complete! You can now run DriveMapper Pro v5.6+")
        except Exception as e:
            print(f"\n✗ Error saving config: {e}")
            print(f"Original backup is at: {BACKUP_FILE}")
    else:
        print("✓ Config is already up to date. No changes needed.")

if __name__ == "__main__":
    print("=" * 60)
    print("DriveMapper Pro Sync Config Migration")
    print("=" * 60)
    migrate_sync_config()
    print("\nPress Enter to exit...")
    input()
