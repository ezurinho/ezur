@echo off
rem Arranca el bot con el perfil que opera: datos reales de OKX, ejecucion en papel.
rem Sin ventana: pythonw deja el servidor en segundo plano y escribe su salida en
rem data\run\engine.log. La cuenta vive en profiles\okx\terminal.db.
setlocal
cd /d "%~dp0"

if not exist "data\run" mkdir "data\run"

if not exist ".venv\Scripts\pythonw.exe" (
  echo Falta .venv: ejecuta start.bat una vez para crearlo.
  exit /b 1
)

rem Si el panel ya responde, no se arranca un segundo motor.
set "CODIGO="
for /f %%c in ('curl -s -o nul -w "%%{http_code}" --max-time 2 http://127.0.0.1:8765/health 2^>nul') do set "CODIGO=%%c"
if "%CODIGO%"=="200" (
  echo ezur ya esta respondiendo en http://127.0.0.1:8765.
  exit /b 0
)

if not exist "frontend\dist\index.html" (
  echo Falta el panel compilado; lo construyo con npm.
  pushd frontend
  call npm install
  call npm run build
  popd
  if not exist "frontend\dist\index.html" (
    echo Aviso: no hay frontend\dist; el panel saldra vacio.
  )
)

set EZUR_PROFILE_DIR=profiles\okx
echo [%date% %time%] arranque del motor >> "data\run\start_paper.log"
start "" /b ".venv\Scripts\pythonw.exe" run.py >> "data\run\engine.log" 2>&1
endlocal
