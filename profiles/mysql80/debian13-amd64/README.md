# MySQL 8.0.46 on Debian 13 amd64

This profile was validated end to end in the offline execution environment on Debian 13 amd64 with Supervisor as PID 1.

## Files

- `request.json`: downloads the official MySQL 8.0.46 minimal generic Linux archive and the required Debian compatibility libraries.
- `install.sh`: verifies all payload SHA-256 values, installs compatibility libraries, installs and configures MySQL, detects the real service manager, secures local root access, and performs a SQL write/read smoke test.

## Validated result

- MySQL: `8.0.46 MySQL Community Server - GPL`
- Listener: `127.0.0.1:3306`
- Service manager: Supervisor
- SQL smoke test: database creation, table creation, upsert, and read succeeded
- Root credentials: `/root/.my.cnf`, mode `0600`
- Receipt: `/etc/mysql/OFFLINE_BRIDGE_INSTALL.json`

## Compatibility dependencies

MySQL's minimal generic binary requires compatibility handling on Debian 13:

- `libaio1t64`, plus a local SONAME compatibility link from `libaio.so.1` to `libaio.so.1t64`
- Debian 12 legacy `libtinfo5`
- Debian 12 legacy `libncurses5`

All downloaded Debian packages are pinned by SHA-256 in `request.json`. The MySQL archive is pinned again by SHA-256 inside `install.sh` and was cross-checked against the MD5 published on the official MySQL download page.
