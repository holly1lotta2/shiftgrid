#!/usr/bin/env sh
# Запуск ShiftGrid на macOS / Linux: ./start.sh
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Первый запуск: создаю окружение .venv..."
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
exec .venv/bin/python run.py
