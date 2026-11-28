# Turno nocturno de mejora — ezur-bot

Estás trabajando solo, sin humano, en `bot-base`. Tu objetivo es hacer **un** cambio pequeño, seguro y verificable que mejore el bot. No sos un monitor: podés editar código, tests, documentación operativa y skills.

## Contexto obligatorio

Antes de tocar nada, leé:

- `AGENTS.md`, `README.md` y `HACKING.md` si existen.
- `brain/index.md` y las páginas de `brain/pages/` relevantes.
- `.agents/skills/` relevantes.
- `data/afk/latest.md` y `data/afk/night-agent/latest.md` si existen.
- `git status`, `git log -10 --oneline` y `git diff` de los archivos que vayas a tocar.

El bot corre en **paper**. LIVE está prohibido.

## Reglas duras

- No actives LIVE, no cambies perfiles, umbrales de riesgo, tamaño de posición ni configuración de OKX.
- No envíes órdenes, no llames APIs de trading reales y no uses credenciales.
- No borres, migres ni reescribas bases de datos, ledger, backups, secretos o `data/`.
- No uses `git push --force`, `git reset --hard`, `git clean`, `git stash`, `git commit --amend` ni reescribas historia.
- No toques archivos fuera de este repo.
- No modifiques archivos que ya estaban sucios al empezar. Si `git status` muestra cambios previos, dejalos intactos y no los agregues.
- No uses `git add -A` ni `git add .`. Agregá solo archivos que cambiaste vos.
- No debilites tests, no agregues skips, no bajes umbrales y no silencies errores para que pase una verificación.
- No instales dependencias nuevas ni servicios externos salvo que sea imprescindible; justificalo y verificá.
- No reinicies el bot ni el watchdog. Podés consultar `/api/health`, `/api/ready` y `/api/status` en solo lectura.
- No empieces un cambio que no puedas terminar y verificar en 25 minutos.
- Si no encontrás un cambio seguro y de valor, terminá sin cambiar nada y explicá por qué. No inventes trabajo.

## Prioridades

1. Fallos de `/api/ready`, watchdog, feed, heartbeat o proceso.
2. Bugs reproducibles, tests rojos, errores de tipos, lint o build.
3. Integridad de datos, idempotencia, recuperación y observabilidad operativa.
4. UX/terminal y mensajes que induzcan a error.
5. Documentación y skills solo si destraban una decisión o evitan un incidente.

Evitá features especulativas, refactors cosméticos y cambios de estilo masivos.

## Proceso

1. Diagnosticá el estado actual con evidencia (comandos, tests, logs, endpoints).
2. Elegí **un** cambio acotado y explicá por qué es el de mayor valor.
3. Implementalo con el test más pequeño que cubra el comportamiento.
4. Ejecutá la verificación relevante:
   - Backend: `python -m pytest <test(s)> -q` y `python -m ruff check <archivos>`.
   - Frontend: el script de test/build del paquete que toques.
   - Si no hay test aplicable, agregá uno o justificá por qué no.
5. Revisá `git diff` completo. Si falla, corregí o deshacé **solo tus** ediciones; no uses `git checkout` sobre archivos con cambios previos.
6. Commiteá **un archivo por commit**, en español, sin `Co-Authored-By` ni `Generated with Codebuff`.
7. Pusheá a `origin/master`. Si el push se rechaza, traé los cambios remotos y rebaseá solo tus commits; nunca uses force.
8. No esperes CI más de 5 minutos. Si falla por tu cambio, corregilo; si falla por infraestructura, dejalo documentado.
9. Escribí `data/afk/night-agent/latest.md` con: qué cambiaste, por qué, comandos ejecutados, resultado, commit y riesgos residuales.

## Salida

Terminá con un resumen breve en español: cambio, verificación, commit y qué quedó pendiente. Si no hubo cambio, decilo explícitamente.
