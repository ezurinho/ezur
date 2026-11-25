@echo off
rem Arranca el bot con el perfil que opera: datos reales de OKX, ejecucion en papel.
rem La cuenta queda en profiles\okx\terminal.db: reiniciar no la borra.
rem Sirve tambien para el Programador de tareas: se coloca en su carpeta (el
rem perfil es relativo), usa el python del venv y no arranca un segundo proceso
rem si el panel ya esta escuchando en el puerto.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Falta .venv: ejecuta start.bat una vez para crearlo.
  exit /b 1
)

netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo ezur ya esta escuchando en http://127.0.0.1:8765; no se arranca otro.
  exit /b 0
)

set EZUR_PROFILE_DIR=profiles\okx
echo ezur en papel con el perfil okx. Panel: http://127.0.0.1:8765
".venv\Scripts\python.exe" run.py
endlocal
