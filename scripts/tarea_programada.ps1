<#
.SYNOPSIS
Registra las tareas programadas "ezur-paper", "ezur-watchdog" y
"ezur-watchdog-keepalive": arrancan el motor, su vigilante y un relanzador
del vigilante cada 5 minutos.

.DESCRIPTION
Las tareas viven fuera del repo (en el Programador de tareas de Windows), asi
que mover la carpeta o reinstalar el sistema las pierde. Este script las vuelve
a crear con las rutas de la copia actual, sin rutas fijas.

"ezur-paper" lanza start_paper.bat (el motor, sin ventana con pythonw).
"ezur-watchdog" lanza scripts\watchdog.py: si el motor deja de responder,
mata solo el proceso que escucha en 8765 y lo relanza. "ezur-watchdog-keepalive"
lo vuelve a lanzar cada 5 minutos: si el propio vigilante murio, el lock hace
que la copia nueva arranque y las copias simultaneas salgan sin hacer nada.

Se usan las cmdlets Register-ScheduledTask en vez de `schtasks /TR`: la ruta
completa de este repo puede superar el limite de 261 caracteres de esa opcion.

.PARAMETER Borrar
Quita las tres tareas en vez de crearlas.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1 -Borrar
#>

param([switch]$Borrar)

$ErrorActionPreference = 'Stop'

# Raiz del repo: este script vive en scripts\.
$raiz = Split-Path $PSScriptRoot -Parent
$bat = Join-Path $raiz 'start_paper.bat'
$pythonw = Join-Path $raiz '.venv\Scripts\pythonw.exe'
$watchdog = Join-Path $raiz 'scripts\watchdog.py'
$usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path $bat)) {
    throw "No encuentro $bat; ejecuta el script desde el repo."
}
if (-not (Test-Path $pythonw)) {
    throw "No encuentro $pythonw; crea el entorno con start.bat."
}
if (-not (Test-Path $watchdog)) {
    throw "No encuentro $watchdog."
}

# El motor primero; el vigilante un minuto despues. El keepalive no depende
# del reloj del vigilante: lo relanza cada 5 minutos y el lock del propio
# watchdog decide si la instancia nueva hace algo o sale.
$tareas = @(
    @{ Nombre = 'ezur-paper';              Ejecutable = $bat;     Argumentos = '';        Retraso = 'PT30S'; CadaMinutos = 0; Descripcion = 'Motor ezur en paper, sin ventana' },
    @{ Nombre = 'ezur-watchdog';           Ejecutable = $pythonw; Argumentos = $watchdog; Retraso = 'PT1M';  CadaMinutos = 0; Descripcion = 'Vigila /api/ready y relanza el servidor si el motor esta running y no responde' },
    @{ Nombre = 'ezur-watchdog-keepalive'; Ejecutable = $pythonw; Argumentos = $watchdog; Retraso = $null;   CadaMinutos = 5; Descripcion = 'Relanza el watchdog cada 5 minutos; el lock evita duplicados' }
)

if ($Borrar) {
    foreach ($t in $tareas) {
        $existente = Get-ScheduledTask -TaskName $t.Nombre -ErrorAction SilentlyContinue
        if (-not $existente) {
            Write-Host "Tarea '$($t.Nombre)' no existe."
            continue
        }
        Unregister-ScheduledTask -TaskName $t.Nombre -Confirm:$false
        Write-Host "Tarea '$($t.Nombre)' borrada."
    }
    return
}

$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -Hidden

foreach ($t in $tareas) {
    $parametrosAccion = @{
        Execute          = $t.Ejecutable
        WorkingDirectory = $raiz
    }
    if ($t.Argumentos) {
        $parametrosAccion.Argument = $t.Argumentos
    }
    $accion = New-ScheduledTaskAction @parametrosAccion

    if ($t.CadaMinutos -gt 0) {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes $t.CadaMinutos)
    } else {
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $usuario
        if ($t.Retraso) {
            $trigger.Delay = $t.Retraso
        }
    }

    Register-ScheduledTask `
        -TaskName $t.Nombre `
        -Action $accion `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description $t.Descripcion `
        -Force | Out-Null
}

# No basta con que Register-ScheduledTask no lance: se lee la tarea registrada
# y se compara la accion y el disparador con esta copia. Una tarea que arranca
# otro fichero, o que se creo pero no repite, es peor que no tener tarea.
foreach ($t in $tareas) {
    $registrada = Get-ScheduledTask -TaskName $t.Nombre -ErrorAction Stop
    $accionRegistrada = @($registrada.Actions)[0]
    $comando = "$($accionRegistrada.Execute)".Trim()
    $argumentos = "$($accionRegistrada.Arguments)".Trim()
    if ($comando -ne $t.Ejecutable) {
        throw "la tarea '$($t.Nombre)' apunta a '$comando' y no a '$($t.Ejecutable)'; no la des por buena."
    }
    if ($t.Argumentos -and $argumentos -notlike "*$($t.Argumentos)*") {
        throw "la tarea '$($t.Nombre)' no pasa '$($t.Argumentos)' (argumentos: '$argumentos')."
    }

    if ($t.CadaMinutos -gt 0) {
        $intervalo = "PT$($t.CadaMinutos)M"
        $repite = @($registrada.Triggers | Where-Object {
            $_.Repetition -and "$($_.Repetition.Interval)" -eq $intervalo
        })
        if (-not $repite) {
            throw "la tarea '$($t.Nombre)' se creo sin repeticion $intervalo; no la des por buena."
        }
    } elseif ($t.Retraso) {
        $logon = @($registrada.Triggers)[0]
        if ("$($logon.Delay)" -ne $t.Retraso) {
            throw "la tarea '$($t.Nombre)' no conserva el retraso $($t.Retraso); no la des por buena."
        }
    }

    Write-Host "Tarea '$($t.Nombre)' creada y verificada: $comando $argumentos"
}

Write-Host ""
Write-Host "  motor:     $bat (30 s tras iniciar sesion; corre sin ventana)"
Write-Host "  vigilante: $pythonw $watchdog (60 s tras iniciar sesion)"
Write-Host "  keepalive: $pythonw $watchdog (cada 5 min; el lock evita duplicados)"
Write-Host "  logs:      data\run\start_paper.log, data\run\engine.log, data\watchdog.log"
Write-Host ""
foreach ($t in $tareas) {
    Get-ScheduledTask -TaskName $t.Nombre | Get-ScheduledTaskInfo |
        Select-Object TaskName, LastRunTime, NextRunTime, LastTaskResult
}
