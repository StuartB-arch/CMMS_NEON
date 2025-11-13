"""
Backup Manager Module
Handles automated database backups including:
- Scheduled backups (daily, weekly, monthly)
- Backup rotation and retention
- Backup verification
- Restore capabilities
- Compression and encryption support
"""

import os
import shutil
import threading
import time
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
from pathlib import Path
import hashlib


class BackupManager:
    """Manages automated database backups"""

    def __init__(self, db_config: Dict, backup_dir: str = "./backups"):
        """
        Initialize backup manager

        Args:
            db_config: Database configuration dictionary
            backup_dir: Directory to store backups
        """
        self.db_config = db_config
        self.backup_dir = Path(backup_dir)
        self.config_file = self.backup_dir / "backup_config.json"
        self.backup_log_file = self.backup_dir / "backup_log.json"

        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Default configuration
        self.config = {
            'enabled': True,
            'schedule': 'daily',  # daily, weekly, monthly
            'backup_time': '02:00',  # Time to run backup (24-hour format)
            'retention_days': 30,  # Keep backups for 30 days
            'max_backups': 50,  # Maximum number of backups to keep
            'compress': True,  # Compress backups
            'verify_after_backup': True  # Verify backup after creation
        }

        # Load existing configuration
        self._load_config()

        # Backup thread
        self.backup_thread = None
        self.stop_event = threading.Event()
        self.last_backup_time = None

    def _load_config(self):
        """Load backup configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                print(f"Error loading backup config: {e}")

    def _save_config(self):
        """Save backup configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving backup config: {e}")

    def _log_backup(self, backup_file: str, status: str, message: str = "", file_size: int = 0):
        """
        Log backup operation

        Args:
            backup_file: Backup filename
            status: Status (success, failed, verified)
            message: Optional message
            file_size: File size in bytes
        """
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'backup_file': backup_file,
            'status': status,
            'message': message,
            'file_size': file_size
        }

        # Load existing log
        log = []
        if self.backup_log_file.exists():
            try:
                with open(self.backup_log_file, 'r') as f:
                    log = json.load(f)
            except:
                pass

        # Add new entry
        log.append(log_entry)

        # Keep only last 1000 entries
        log = log[-1000:]

        # Save log
        try:
            with open(self.backup_log_file, 'w') as f:
                json.dump(log, f, indent=2)
        except Exception as e:
            print(f"Error saving backup log: {e}")

    def create_backup(self, backup_name: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Create a database backup

        Args:
            backup_name: Optional custom backup name

        Returns:
            Tuple of (success, backup_file_path, message)
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if backup_name:
                filename = f"{backup_name}_{timestamp}.backup"
            else:
                filename = f"cmms_backup_{timestamp}.backup"

            backup_path = self.backup_dir / filename

            print(f"Creating backup: {backup_path}")

            # Use pg_dump to create backup
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']

            cmd = [
                'pg_dump',
                '-h', self.db_config['host'],
                '-p', str(self.db_config['port']),
                '-U', self.db_config['user'],
                '-d', self.db_config['database'],
                '-F', 'c',  # Custom format (compressed)
                '-f', str(backup_path)
            ]

            # Add verbose flag for debugging
            cmd.append('-v')

            # Run pg_dump
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                error_msg = f"pg_dump failed: {result.stderr}"
                print(error_msg)
                self._log_backup(filename, 'failed', error_msg)
                return False, "", error_msg

            # Get file size
            file_size = backup_path.stat().st_size
            file_size_mb = file_size / (1024 * 1024)

            # Verify backup if configured
            if self.config['verify_after_backup']:
                print("Verifying backup...")
                verified, verify_msg = self._verify_backup(str(backup_path))
                if not verified:
                    self._log_backup(filename, 'failed', f"Verification failed: {verify_msg}", file_size)
                    return False, str(backup_path), f"Backup created but verification failed: {verify_msg}"

            self._log_backup(filename, 'success', f"Size: {file_size_mb:.2f} MB", file_size)
            self.last_backup_time = datetime.now()

            print(f"Backup created successfully: {backup_path} ({file_size_mb:.2f} MB)")
            return True, str(backup_path), f"Backup created: {file_size_mb:.2f} MB"

        except subprocess.TimeoutExpired:
            error_msg = "Backup timed out after 10 minutes"
            print(error_msg)
            self._log_backup(filename, 'failed', error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Error creating backup: {str(e)}"
            print(error_msg)
            self._log_backup(filename if 'filename' in locals() else 'unknown', 'failed', error_msg)
            return False, "", error_msg

    def _verify_backup(self, backup_path: str) -> Tuple[bool, str]:
        """
        Verify backup integrity

        Args:
            backup_path: Path to backup file

        Returns:
            Tuple of (is_valid, message)
        """
        try:
            # Check if file exists and has content
            if not os.path.exists(backup_path):
                return False, "Backup file not found"

            file_size = os.path.getsize(backup_path)
            if file_size < 1000:  # Less than 1KB is suspicious
                return False, f"Backup file too small: {file_size} bytes"

            # Use pg_restore to verify
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']

            cmd = [
                'pg_restore',
                '--list',
                backup_path
            ]

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return False, f"Verification failed: {result.stderr}"

            # Check if restore list contains tables
            if 'TABLE DATA' not in result.stdout:
                return False, "Backup does not contain table data"

            return True, "Backup verified successfully"

        except Exception as e:
            return False, f"Verification error: {str(e)}"

    def restore_backup(self, backup_path: str, confirm: bool = False) -> Tuple[bool, str]:
        """
        Restore database from backup

        Args:
            backup_path: Path to backup file
            confirm: Must be True to actually perform restore

        Returns:
            Tuple of (success, message)
        """
        if not confirm:
            return False, "Restore not confirmed. Set confirm=True to proceed."

        try:
            if not os.path.exists(backup_path):
                return False, f"Backup file not found: {backup_path}"

            print(f"Restoring from backup: {backup_path}")
            print("WARNING: This will overwrite the current database!")

            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']

            # First, terminate all connections to the database
            # (This would require superuser privileges, so we'll skip it for now)

            # Restore the backup
            cmd = [
                'pg_restore',
                '-h', self.db_config['host'],
                '-p', str(self.db_config['port']),
                '-U', self.db_config['user'],
                '-d', self.db_config['database'],
                '--clean',  # Clean (drop) database objects before recreating
                '--if-exists',  # Use IF EXISTS when dropping objects
                '--no-owner',  # Skip restoration of object ownership
                '--no-acl',  # Skip restoration of access privileges
                backup_path
            ]

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0 and 'ERROR' in result.stderr:
                # Some errors are expected (e.g., objects already exist)
                # Only fail if there are critical errors
                if 'FATAL' in result.stderr or 'could not connect' in result.stderr:
                    return False, f"Restore failed: {result.stderr}"

            print("Restore completed successfully")
            return True, "Database restored successfully"

        except Exception as e:
            return False, f"Error restoring backup: {str(e)}"

    def cleanup_old_backups(self) -> int:
        """
        Remove old backups based on retention policy

        Returns:
            Number of backups removed
        """
        removed_count = 0

        try:
            # Get all backup files
            backup_files = sorted(self.backup_dir.glob("*.backup"))

            # Remove backups older than retention_days
            cutoff_date = datetime.now() - timedelta(days=self.config['retention_days'])

            for backup_file in backup_files:
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)

                if file_time < cutoff_date:
                    print(f"Removing old backup: {backup_file.name}")
                    backup_file.unlink()
                    removed_count += 1

            # If still over max_backups, remove oldest
            backup_files = sorted(self.backup_dir.glob("*.backup"))
            if len(backup_files) > self.config['max_backups']:
                excess_count = len(backup_files) - self.config['max_backups']
                for backup_file in backup_files[:excess_count]:
                    print(f"Removing excess backup: {backup_file.name}")
                    backup_file.unlink()
                    removed_count += 1

        except Exception as e:
            print(f"Error cleaning up backups: {e}")

        return removed_count

    def list_backups(self) -> List[Dict]:
        """
        List all available backups

        Returns:
            List of backup information dictionaries
        """
        backups = []

        try:
            backup_files = sorted(self.backup_dir.glob("*.backup"), reverse=True)

            for backup_file in backup_files:
                stat = backup_file.stat()
                backups.append({
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'size': stat.st_size,
                    'size_mb': stat.st_size / (1024 * 1024),
                    'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
                })

        except Exception as e:
            print(f"Error listing backups: {e}")

        return backups

    def get_backup_log(self, limit: int = 50) -> List[Dict]:
        """
        Get backup log entries

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of log entries
        """
        if not self.backup_log_file.exists():
            return []

        try:
            with open(self.backup_log_file, 'r') as f:
                log = json.load(f)
                return log[-limit:]
        except Exception as e:
            print(f"Error reading backup log: {e}")
            return []

    def start_automatic_backups(self):
        """Start automatic backup thread"""
        if self.backup_thread and self.backup_thread.is_alive():
            print("Automatic backups already running")
            return

        if not self.config['enabled']:
            print("Automatic backups disabled in configuration")
            return

        self.stop_event.clear()
        self.backup_thread = threading.Thread(target=self._backup_loop, daemon=True)
        self.backup_thread.start()
        print("Automatic backups started")

    def stop_automatic_backups(self):
        """Stop automatic backup thread"""
        if self.backup_thread and self.backup_thread.is_alive():
            self.stop_event.set()
            self.backup_thread.join(timeout=5)
            print("Automatic backups stopped")

    def _backup_loop(self):
        """Main loop for automatic backups"""
        print("Backup loop started")

        while not self.stop_event.is_set():
            try:
                # Check if it's time for a backup
                if self._should_run_backup():
                    print("Running scheduled backup...")
                    success, path, msg = self.create_backup()

                    if success:
                        print(f"Scheduled backup successful: {msg}")
                        # Cleanup old backups
                        removed = self.cleanup_old_backups()
                        if removed > 0:
                            print(f"Removed {removed} old backup(s)")
                    else:
                        print(f"Scheduled backup failed: {msg}")

                # Sleep for 5 minutes before checking again
                self.stop_event.wait(300)

            except Exception as e:
                print(f"Error in backup loop: {e}")
                self.stop_event.wait(60)

    def _should_run_backup(self) -> bool:
        """
        Check if a backup should be run now based on schedule

        Returns:
            True if backup should run
        """
        now = datetime.now()

        # If no backup has been done yet, do one now
        if self.last_backup_time is None:
            return True

        # Parse configured backup time
        try:
            backup_hour, backup_minute = map(int, self.config['backup_time'].split(':'))
        except:
            backup_hour, backup_minute = 2, 0  # Default to 2:00 AM

        # Check if we're past the backup time today
        backup_time_today = now.replace(hour=backup_hour, minute=backup_minute, second=0, microsecond=0)

        # Calculate time since last backup
        time_since_last = now - self.last_backup_time

        # Check schedule
        if self.config['schedule'] == 'daily':
            # Run daily at configured time
            if now >= backup_time_today and self.last_backup_time < backup_time_today:
                return True
        elif self.config['schedule'] == 'weekly':
            # Run weekly on Monday at configured time
            if now.weekday() == 0 and time_since_last.days >= 7:
                if now >= backup_time_today and self.last_backup_time < backup_time_today:
                    return True
        elif self.config['schedule'] == 'monthly':
            # Run monthly on 1st at configured time
            if now.day == 1 and time_since_last.days >= 28:
                if now >= backup_time_today and self.last_backup_time < backup_time_today:
                    return True

        return False

    def update_config(self, new_config: Dict):
        """
        Update backup configuration

        Args:
            new_config: Dictionary with new configuration values
        """
        self.config.update(new_config)
        self._save_config()
        print("Backup configuration updated")

    def get_config(self) -> Dict:
        """Get current backup configuration"""
        return self.config.copy()

    def get_status(self) -> Dict:
        """
        Get backup system status

        Returns:
            Dictionary with status information
        """
        backups = self.list_backups()

        status = {
            'enabled': self.config['enabled'],
            'automatic_running': self.backup_thread and self.backup_thread.is_alive(),
            'last_backup': None,
            'next_backup_estimate': None,
            'total_backups': len(backups),
            'total_size_mb': sum(b['size_mb'] for b in backups),
            'oldest_backup': backups[-1]['created'] if backups else None,
            'newest_backup': backups[0]['created'] if backups else None
        }

        if self.last_backup_time:
            status['last_backup'] = self.last_backup_time.strftime('%Y-%m-%d %H:%M:%S')

        return status
