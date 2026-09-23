# Roadmap / ideas

Pick anything here - comment on (or open) an issue first so we don't duplicate work.

## Good first issues
- [ ] Split the single 1,700-line `drivemapper_pro.py` into modules (UI / mapping / sync / config)
- [ ] Add a `--version` flag and show the version in one place instead of several strings
- [ ] Convert the `.txt` guides to Markdown
- [x] Add screenshots to the README

## Security (highest priority)
- [x] Store share passwords in Windows Credential Manager (`keyring`) instead of plain-text `network_vault.json`
- [ ] Redact usernames/IPs in `drive_events.log`
- [ ] `rclone`/NFS mounts pass the password on the command line (visible to other local processes) - use a safer mechanism

## Features
- [ ] Auto-reconnect drives at logon / scheduled task
- [ ] Import/export profiles
- [ ] Dark/light theme toggle
- [ ] Scheduled sync jobs
- [ ] NFS and SFTP mapping helpers
- [ ] Unit tests for the config and sync-command builders
- [ ] GitHub Actions: lint + build the `.exe` on every tagged release
