#!/bin/bash
# Выкатка новой версии по схеме «папки версий + ярлык current».
#
# Запуск:   deploy.sh <папка-с-новой-версией>
# Пример:   deploy.sh /tmp/build-a1b2c3d
#
# Что настраивается переменными окружения:
#   APP_DIR      - корень проекта на сервере (по умолчанию /opt/moy-servis)
#   RESTART_CMD  - как перезапустить сервис
#   CHECK_CMD    - как проверить, что сервис работает (код 0 = работает)
#   KEEP         - сколько версий хранить (по умолчанию 5)
#   TRIES, PAUSE - сколько раз и с какой паузой (в секундах) проверять после перезапуска
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/moy-servis}"
RESTART_CMD="${RESTART_CMD:-sudo systemctl restart moy-servis.service}"
CHECK_CMD="${CHECK_CMD:-curl --fail --silent --max-time 5 http://127.0.0.1:8080/health}"
KEEP="${KEEP:-5}"
TRIES="${TRIES:-6}"
PAUSE="${PAUSE:-5}"
SRC="${1:?укажите папку с новой версией}"

# Стоп-кран: пока лежит файл FREEZE, выкатка не идёт.
if [ -e "$APP_DIR/FREEZE" ]; then
  echo "Выкатка остановлена: найден $APP_DIR/FREEZE" >&2
  exit 3
fi

release="$APP_DIR/releases/$(date -u +%Y-%m-%d-%H%M%S)"
previous="$(readlink "$APP_DIR/current" 2>/dev/null || true)"

# 1. Новая версия ложится в новую папку. Действующая не тронута.
mkdir -p "$APP_DIR/releases"
cp -R "$SRC" "$release"
chmod -R a-w "$release"            # версия неизменна: править в ней нечего

# 2. Ярлык переключается на новую папку.
ln -sfn "$release" "$APP_DIR/current"

# 3. Перезапуск и проверка состояния. Сообщению команды не верим, спрашиваем сервис.
#    Если сам перезапуск вернул ошибку, проверку пропускаем и сразу идём на откат.
ok=0
restarted=1
$RESTART_CMD || restarted=0
for _ in $(seq 1 "$TRIES"); do
  [ "$restarted" -eq 1 ] || break
  if $CHECK_CMD >/dev/null 2>&1; then ok=1; break; fi
  sleep "$PAUSE"
done

# 4. Проверка не прошла - возвращаем ярлык на предыдущую версию.
if [ "$ok" -ne 1 ]; then
  echo "Новая версия не прошла проверку." >&2
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$APP_DIR/current"
    $RESTART_CMD || echo "Перезапуск предыдущей версии тоже не удался: нужен человек." >&2
    echo "Ярлык возвращён на $previous" >&2
  else
    echo "Предыдущей версии нет, откатываться некуда." >&2
  fi
  exit 1
fi

# 5. Уборка: храним только последние KEEP версий.
total=$(find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
if [ "$total" -gt "$KEEP" ]; then
  find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d | sort | head -n "$((total - KEEP))" |
    while read -r old; do chmod -R u+w "$old" && rm -rf "$old"; done
fi

echo "Выкачено: $release"
