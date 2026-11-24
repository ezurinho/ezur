@echo off
rem Arranca el bot con el perfil que opera: datos reales de OKX, ejecucion en papel.
rem La cuenta queda en profiles\okx\terminal.db: reiniciar no la borra.
setlocal
call .venv\Scripts\activate.bat
set EZUR_PROFILE_DIR=profiles\okx
python run.py
endlocal
