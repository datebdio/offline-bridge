#!/usr/bin/env bash
set -Eeuo pipefail

MYSQL_VERSION="8.0.46"
PROFILE="mysql80-debian13-amd64"
PAYLOAD_DIR="${1:-}"
MYSQL_TARBALL="${PAYLOAD_DIR}/downloads/mysql-8.0.46-linux-glibc2.17-x86_64-minimal.tar.xz"
LIBAIO_DEB="${PAYLOAD_DIR}/downloads/libaio1t64_0.3.113-8+b1_amd64.deb"
LIBTINFO_DEB="${PAYLOAD_DIR}/downloads/libtinfo5_6.4-4_amd64.deb"
LIBNCURSES_DEB="${PAYLOAD_DIR}/downloads/libncurses5_6.4-4_amd64.deb"
MYSQL_SHA256="e2777d490fcaadc5a4be06db89b6935c78909bd9c3382af859ab284af0c950b0"
LIBAIO_SHA256="490c8a2d116001a5f3b0a6d7a7aabf6a7b629366590dc5c3f75b078e931dd129"
LIBTINFO_SHA256="dd347f794e651039e7b4c391f86c674fed7f415b3dca6b0937beb0d470f09c1a"
LIBNCURSES_SHA256="02f4f7f52c4ce2fc4021793a931bfd85f7870554b8e4d56576d73a4ed0bdb390"

log() { printf '[offline-bridge:mysql] %s\n' "$*"; }
die() { printf '[offline-bridge:mysql] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "run as root"
[[ -n "${PAYLOAD_DIR}" && -d "${PAYLOAD_DIR}" ]] || die "usage: $0 <verified-payload-directory>"
. /etc/os-release
[[ "${ID:-}" == "debian" && "${VERSION_ID:-}" == "13" ]] || die "profile requires Debian 13; found ${ID:-unknown} ${VERSION_ID:-unknown}"
[[ "$(dpkg --print-architecture)" == "amd64" ]] || die "profile requires amd64"

verify() {
  local file="$1" expected="$2"
  [[ -f "$file" ]] || die "missing payload file: $file"
  local actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || die "SHA-256 mismatch for $(basename "$file"): $actual"
}

log "verifying payload"
verify "$MYSQL_TARBALL" "$MYSQL_SHA256"
verify "$LIBAIO_DEB" "$LIBAIO_SHA256"
verify "$LIBTINFO_DEB" "$LIBTINFO_SHA256"
verify "$LIBNCURSES_DEB" "$LIBNCURSES_SHA256"

log "installing runtime compatibility packages"
dpkg -i "$LIBAIO_DEB" "$LIBTINFO_DEB" "$LIBNCURSES_DEB" >/tmp/offline-bridge-mysql-dpkg.log 2>&1 || {
  cat /tmp/offline-bridge-mysql-dpkg.log >&2
  die "compatibility package installation failed"
}
# Debian 13 renamed the libaio SONAME to libaio.so.1t64 while MySQL 8.0 expects libaio.so.1.
ln -sfn /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1
ldconfig

log "installing MySQL ${MYSQL_VERSION}"
if [[ ! -x "/opt/mysql-${MYSQL_VERSION}/bin/mysqld" ]]; then
  rm -rf "/opt/mysql-${MYSQL_VERSION}"
  tar -xJf "$MYSQL_TARBALL" -C /opt
  mv "/opt/mysql-${MYSQL_VERSION}-linux-glibc2.17-x86_64-minimal" "/opt/mysql-${MYSQL_VERSION}"
fi
ln -sfn "/opt/mysql-${MYSQL_VERSION}" /opt/mysql
for bin in mysql mysqladmin mysqldump mysqlcheck mysqlshow; do
  ln -sfn "/opt/mysql/bin/${bin}" "/usr/local/bin/${bin}"
done

missing="$(ldd /opt/mysql/bin/mysqld /opt/mysql/bin/mysql 2>/dev/null | awk '/not found/{print $1}' | sort -u | tr '\n' ' ')"
[[ -z "$missing" ]] || die "unresolved shared libraries: $missing"

getent group mysql >/dev/null || groupadd --system mysql
getent passwd mysql >/dev/null || useradd --system --gid mysql --home-dir /var/lib/mysql --shell /usr/sbin/nologin mysql
install -d -o mysql -g mysql -m 750 /var/lib/mysql /var/lib/mysql-files /var/run/mysqld /var/log/mysql
install -d -m 755 /etc/mysql
cat >/etc/mysql/my.cnf <<'CNF'
[mysqld]
basedir=/opt/mysql
datadir=/var/lib/mysql
socket=/var/run/mysqld/mysqld.sock
pid-file=/var/run/mysqld/mysqld.pid
port=3306
bind-address=127.0.0.1
mysqlx-bind-address=127.0.0.1
user=mysql
log-error=/var/log/mysql/error.log
secure-file-priv=/var/lib/mysql-files
skip-name-resolve

[client]
socket=/var/run/mysqld/mysqld.sock
port=3306
CNF
chmod 644 /etc/mysql/my.cnf

if [[ ! -d /var/lib/mysql/mysql ]]; then
  log "initializing data directory"
  rm -rf /var/lib/mysql/*
  /opt/mysql/bin/mysqld --defaults-file=/etc/mysql/my.cnf --initialize-insecure
fi

start_with_supervisor() {
  local supervisor_conf=""
  if [[ -r /proc/1/cmdline ]] && tr '\0' ' ' </proc/1/cmdline | grep -q supervisord; then
    supervisor_conf="$(tr '\0' '\n' </proc/1/cmdline | awk 'prev=="-c"{print; exit}{prev=$0}')"
    [[ -n "$supervisor_conf" ]] || supervisor_conf=/etc/supervisord.conf
  fi
  [[ -n "$supervisor_conf" && -f "$supervisor_conf" ]] || return 1
  install -d -m 755 /etc/supervisor/conf.d
  if ! grep -q '^\[include\]' "$supervisor_conf"; then
    cat >>"$supervisor_conf" <<'INC'

[include]
files = /etc/supervisor/conf.d/*.conf
INC
  fi
  cat >/etc/supervisor/conf.d/mysql.conf <<'SUP'
[program:mysql]
command=/opt/mysql/bin/mysqld --defaults-file=/etc/mysql/my.cnf
directory=/opt/mysql
user=mysql
autostart=true
autorestart=true
startsecs=5
startretries=3
stopsignal=TERM
stopwaitsecs=60
stdout_logfile=/var/log/mysql/supervisor-out.log
stderr_logfile=/var/log/mysql/supervisor-err.log
environment=PATH="/opt/mysql/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SUP
  supervisorctl reread >/dev/null
  supervisorctl update >/dev/null
  supervisorctl start mysql >/dev/null 2>&1 || true
  return 0
}

start_with_systemd() {
  [[ "$(ps -p 1 -o comm= 2>/dev/null | xargs)" == "systemd" ]] || return 1
  cat >/etc/systemd/system/mysql.service <<'UNIT'
[Unit]
Description=MySQL Community Server 8.0
After=network.target

[Service]
Type=notify
User=mysql
Group=mysql
ExecStart=/opt/mysql/bin/mysqld --defaults-file=/etc/mysql/my.cnf
TimeoutSec=0
LimitNOFILE=10000
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now mysql
}

if ! mysqladmin --defaults-file=/etc/mysql/my.cnf -uroot ping >/dev/null 2>&1; then
  log "starting MySQL service"
  start_with_supervisor || start_with_systemd || {
    nohup runuser -u mysql -- /opt/mysql/bin/mysqld --defaults-file=/etc/mysql/my.cnf \
      >>/var/log/mysql/manual-start.log 2>&1 &
  }
fi

for _ in $(seq 1 30); do
  if mysqladmin --defaults-file=/etc/mysql/my.cnf -uroot ping >/dev/null 2>&1; then break; fi
  if [[ -f /root/.my.cnf ]] && mysqladmin --defaults-file=/root/.my.cnf ping >/dev/null 2>&1; then break; fi
  sleep 1
done

if [[ -f /root/.my.cnf ]]; then
  CLIENT=(mysql --defaults-file=/root/.my.cnf)
  ADMIN=(mysqladmin --defaults-file=/root/.my.cnf)
else
  CLIENT=(mysql --defaults-file=/etc/mysql/my.cnf -uroot)
  ADMIN=(mysqladmin --defaults-file=/etc/mysql/my.cnf -uroot)
fi
"${ADMIN[@]}" ping >/dev/null || { tail -100 /var/log/mysql/error.log >&2; die "MySQL did not become ready"; }

if [[ ! -f /root/.my.cnf ]]; then
  root_password="$(openssl rand -hex 18)"
  "${CLIENT[@]}" -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${root_password}';"
  cat >/root/.my.cnf <<EOF2
[client]
user=root
password=${root_password}
socket=/var/run/mysqld/mysqld.sock
EOF2
  chmod 600 /root/.my.cnf
  CLIENT=(mysql --defaults-file=/root/.my.cnf)
  ADMIN=(mysqladmin --defaults-file=/root/.my.cnf)
fi

log "running SQL smoke test"
result="$("${CLIENT[@]}" --batch --skip-column-names -e "CREATE DATABASE IF NOT EXISTS offline_bridge_test; USE offline_bridge_test; CREATE TABLE IF NOT EXISTS probe(id INT PRIMARY KEY, note VARCHAR(64)); INSERT INTO probe VALUES(1,'offline bridge works') ON DUPLICATE KEY UPDATE note=VALUES(note); SELECT VERSION(), id, note FROM probe WHERE id=1;")"
[[ "$result" == *"${MYSQL_VERSION}"* && "$result" == *"offline bridge works"* ]] || die "SQL smoke test failed: $result"

service_manager="manual"
if supervisorctl status mysql >/dev/null 2>&1; then service_manager="supervisor"; fi
if [[ "$(ps -p 1 -o comm= 2>/dev/null | xargs)" == "systemd" ]]; then service_manager="systemd"; fi
cat >/etc/mysql/OFFLINE_BRIDGE_INSTALL.json <<EOF2
{
  "status": "verified",
  "profile": "${PROFILE}",
  "mysql_version": "${MYSQL_VERSION}",
  "bind_address": "127.0.0.1",
  "port": 3306,
  "service_manager": "${service_manager}",
  "root_client_config": "/root/.my.cnf"
}
EOF2
chmod 644 /etc/mysql/OFFLINE_BRIDGE_INSTALL.json

log "MySQL ${MYSQL_VERSION} is installed, secured, running, and SQL-verified"
"${ADMIN[@]}" ping
"${CLIENT[@]}" --batch --skip-column-names -e "SELECT VERSION(), @@version_comment, @@port, @@socket;"
