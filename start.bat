@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title ShiftGrid

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :no_python

if exist ".venv\Scripts\python.exe" goto :install
echo Первый запуск: создаю окружение .venv, это займёт около минуты...
%PY% -m venv .venv || goto :error

:install
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :error
".venv\Scripts\python.exe" run.py
goto :end

:no_python
echo Python не найден. Установите Python 3.10 или новее: https://www.python.org/downloads/
echo При установке отметьте галочку "Add python.exe to PATH", затем снова запустите start.bat.
goto :end

:error
echo.
echo Не удалось запустить ShiftGrid. Причина написана выше.

:end
echo.
pause
