@echo off
rem Arranca el bot con el perfil que opera: datos reales de OKX, ejecucion en papel.
rem La cuenta queda en profiles\okx\terminal.db: reiniciar no la borra.
rem Sin ventana: la primera pasada se relanza oculta y todo ocurre detras.
rem Logs: data\run\start_paper.log (decisiones del arranque) y
rem data\run\engine.log (salida del motor, que lo mantiene abierto).
setlocal
cd /d "%~dp0"

if not defined EZUR_HIDDEN (
  set "EZUR_HIDDEN=1"
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WindowStyle Hidden"
  exit /b 0
)

if not exist "data\run" mkdir "data\run"
set "START_LOG=data\run\start_paper.log"

if not exist ".venv\Scripts\python.exe" (
  echo [%date% %time%] falta .venv: ejecuta start.bat una vez >> "%START_LOG%"
  exit /b 1
)

rem Solo se salta el arranque si el panel responde de verdad: un socket
rem LISTENING que sobrevive al proceso anterior no debe dejarnos sin motor.
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8765/health; exit ([int]($r.StatusCode -ne 200)) } catch { exit 1 }"
if not errorlevel 1 (
  echo [%date% %time%] ya habia un motor respondiendo; no se arranca otro >> "%START_LOG%"
  exit /b 0
)

if not exist "frontend\dist\index.html" (
  echo [%date% %time%] falta el panel compilado; lo construyo con npm >> "%START_LOG%"
  pushd frontend
  call npm install >> "..\data\run\start_paper.log" 2>&1
  call npm run build >> "..\data\run\start_paper.log" 2>&1
  popd
  if not exist "frontend\dist\index.html" (
    echo [%date% %time%] aviso: no hay frontend\dist, el panel saldra vacio >> "%START_LOG%"
  )
)

set EZUR_PROFILE_DIR=profiles\okx
echo [%date% %time%] arranque del motor >> "%START_LOG%"
".venv\Scripts\python.exe" run.py >> "data\run\engine.log" 2>&1
endlocal
