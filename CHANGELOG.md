# Changelog

Reconstructed from the original development history (February 2026). Older builds are kept
outside this repo; see "History" in the README of the archive if you need them.

## [6.0] - 2026-02-10
- Fix: use `win32file.GetDriveType` (was incorrectly called on `win32api`), fixing drive-type detection
- Example server addresses in built-in help/placeholders replaced with neutral values
- Retitled to v6.0

## [5.6] - 2026-02-07
- Full Sync Manager: rclone (bisync/sync) and robocopy (mirror/copy), saved sync profiles
- `migrate_sync_config.py` to upgrade existing profile files

## [5.3] - 2026-02-07
- Error 1219 fix edition (conflicting credentials to the same server)

## [5.1 - 5.2] - 2026-02-04 to 2026-02-06
- "Full Technician Suite": clone drives, Wake-on-LAN, server management

## [4.x] - 2026-02-04
- 4.0 validation and cloud master; 4.2 full restoration; 4.3 thread-safe discovery; 4.4 rclone guide

## [3.x] - 2026-02-04
- 3.2 first enterprise-style UI; 3.3 unified control; 3.5 unified dashboard; 3.8 event logging; 3.9 full dashboard
