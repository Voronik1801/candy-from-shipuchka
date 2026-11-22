#!/bin/bash
# Хук Claude Code (событие PreToolUse, инструмент Bash).
# Останавливает `git commit` и `git push`, если открыта ветка main или master.
#
# Как работает: Claude Code передаёт описание действия на стандартный вход в виде JSON.
# Код возврата 2 блокирует действие, а текст из потока ошибок показывается агенту.
# Любой другой ненулевой код действие НЕ блокирует, поэтому при собственных сбоях
# скрипт тоже завершается кодом 2: лучше лишний раз остановить, чем пропустить.

input=$(cat)

command=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    sys.exit(1)
') || {
  echo "guard-main: не удалось разобрать входные данные хука, действие остановлено" >&2
  exit 2
}

# Интересуют только коммит и отправка.
case "$command" in
  *"git commit"*|*"git push"*) ;;
  *) exit 0 ;;
esac

# Вне репозитория проверять нечего.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# В только что созданном репозитории коммитов ещё нет: самый первый коммит
# разрешён в любую ветку, иначе main не из чего создать.
git rev-parse --verify -q HEAD >/dev/null 2>&1 || exit 0

# Имя открытой ветки. Пусто, если открыт отдельный коммит, а не ветка.
branch=$(git symbolic-ref --short -q HEAD || true)

if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  echo "Открыта ветка $branch. Коммит и отправка в неё напрямую запрещены." >&2
  echo "Создай ветку по номеру задачи: git checkout -b <владелец>/<номер>-<описание>" >&2
  exit 2
fi

exit 0
