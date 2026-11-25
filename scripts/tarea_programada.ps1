<#
.SYNOPSIS
Registra la tarea programada "ezur-paper": arranca start_paper.bat al iniciar
sesion, 30 s mas tarde, sin ventana.

.DESCRIPTION
La tarea vive fuera del repo (en el Programador de tareas de Windows), asi que
mover la carpeta o reinstalar el sistema la pierde. Este script la vuelve a
crear con las rutas de la copia actual, sin rutas fijas.

.PARAMETER Borrar
Quita la tarea en vez de crearla.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1 -Borrar
#>

param([switch]$Borrar)

$ErrorActionPreference = 'Stop'
$nombre = 'ezur-paper'

# Raiz del repo: este script vive en scripts\.
$raiz = Split-Path $PSScriptRoot -Parent
$bat = Join-Path $raiz 'start_paper.bat'

if (-not (Test-Path $bat)) {
    throw "No encuentro $bat; ejecuta el script desde el repo."
}

if ($Borrar) {
    schtasks.exe /Delete /TN $nombre /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks no pudo borrar la tarea (codigo $LASTEXITCODE)."
    }
    Write-Host "Tarea '$nombre' borrada."
    return
}

# La tarea oculta la ventana: el .bat ya se relanza oculto, pero la tarea
# abre una consola mientras tanto si se lanza a pelo. Sin comillas dobles: dentro
# de /TR rompen el argumento, y la ruta entre comillas simples basta aunque
# tenga espacios.
$accion = "powershell -NoProfile -WindowStyle Hidden -Command Start-Process -FilePath '$bat' -WindowStyle Hidden"

schtasks.exe /Create /TN $nombre /TR $accion /SC ONLOGON /DELAY 0000:30 /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "schtasks no pudo crear la tarea (codigo $LASTEXITCODE)."
}

Write-Host "Tarea '$nombre' creada."
Write-Host "  arranca: $bat (oculto, 30 s tras iniciar sesion)"
Write-Host "  logs:    data\run\start_paper.log y data\run\engine.log"
Write-Host ""
schtasks.exe /Query /TN $nombre /FO LIST
