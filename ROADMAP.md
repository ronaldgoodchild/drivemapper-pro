# Roadmap / ideas

Pick anything here - comment on (or open) an issue first so we don't duplicate work.

## Good first issues
- [ ] Split the single 1,700-line `drivemapper_pro.py` into modules (UI / mapping / sync / config)
- [ ] Add a `--version` flag and show the version in one place instead of several strings
- [ ] Convert the `.txt` guides to Markdown
- [ ] Add screenshots to the README

## Security (highest priority)
- [ ] Store share passwords in Windows Credential Manager (`keyring`) instead of plain-text `network_vault.json`
- [ ] Redact usernames/IPs in `drive_events.log`

## Features
- [ ] Auto-reconnect drives at logon / scheduled task
- [ ] Import/export profiles
- [ ] Dark/light theme toggle
- [ ] Scheduled sync jobs
- [ ] NFS and SFTP mapping helpers
- [ ] Unit tests for the config and sync-command builders
- [ ] GitHub Actions: lint + build the `.exe` on every tagged release
