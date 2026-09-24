#!/usr/bin/env bash
# Деплой «КабинетаЗаочника» на домашний сервер.
# Запускается на сервере от имени непривилегированного пользователя cabinet:
#   sudo -u cabinet bash /var/www/student-cabinet-mvp/deploy/deploy.sh
#
# Делает: venv (если нет) -> pip install по requirements.txt -> рестарт сервиса.

set -euo pipefail

APP_DIR="/var/www/student-cabinet-mvp"
SERVICE="student-cabinet"

cd "$APP_DIR"

VENV="$APP_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Создаю venv"
    python3 -m venv "$VENV"
fi

echo "==> Устанавливаю зависимости"
"$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Перезапускаю $SERVICE"
sudo /usr/bin/systemctl restart "$SERVICE"

sleep 2
echo "==> Состояние: $(systemctl is-active "$SERVICE" || true)"
echo "==> Готово"
