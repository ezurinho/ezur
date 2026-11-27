# Reglas del proyecto

## Commits

- **Sin atribución de IA.** Nada de `Co-Authored-By: Codebuff`, `Generated with Codebuff` ni ninguna línea de footer equivalente. En GitHub tiene que aparecer solo el autor del repositorio. El historial ya se limpió una vez; no se vuelve a ensuciar.
- Mensaje en español, una o dos frases centradas en el porqué.
- Un fichero por commit. Nunca `git add -A` ni `git add .`.
- No reescribir historial ni forzar push sin que lo pida el usuario.

## GitHub

- El repositorio remoto es la fuente de verdad: trabajar siempre contra `origin/master`.
- Después de cada cambio verificado, commit y push **en la misma sesión**, sin esperar a que el usuario lo pida. No dejar commits solo en local ni cambios sin subir al terminar.

## Operación

- Paper trading únicamente: `live_enabled` se queda en `false`.
- No inventar métricas: cada cifra sale de un comando ejecutado y su salida real.
- No relajar puertas ni tests para que algo pase.

<!-- BEGIN brain.md -->
## Project Brain

This project keeps a **Project Brain**: a persistent memory layer of its durable decisions, requirements, and constraints. Read `./BRAIN.md` for the full read/write contract.

The `brain` CLI is not guaranteed to be on `PATH`. From the project root, invoke it as `node <brain-page-skill-dir>/bin/brain.mjs <subcommand> [flags]`, resolving `<brain-page-skill-dir>` to the installed `brain-page` skill directory.

Maintain the brain as part of normal coding work — not as a separate task. While discussing or implementing features:
- **Start of a task:** load relevant context with the `brain` CLI (`list-pages`, `read-page`, `read-root`). Prefer a narrow read over scanning everything.
- **When a decision, requirement, constraint, or durable insight settles** (in chat or while coding): capture it immediately via the `brain` CLI. Do not wait to be asked and do not batch it for later.
- **Pure implementation with no new decision:** do not write to the brain.
- **When overturning a prior conclusion:** update the page (`update-truth` and/or `append-timeline` with `kind: reversal`, or `archive-page`).
- Only store what will still matter in six months and is hard to reconstruct from the code alone.
- Never hand-edit brain files. If a brain MCP server is connected and authenticated, prefer it; otherwise use the `brain` CLI.

The brain skills (`brain-setup`, `brain-page`, `brain-ingest`, `brain-bootstrap`) are installed in your global skills directory. To scaffold a new project, run `node <brain-page-skill-dir>/bin/brain.mjs init` from its root.

If native notes/history are available, keep relevant brain page IDs and unresolved task state in notes; search history for earlier task evidence. After context rollover, re-read relevant pages through the CLI for current project facts. Do not copy task history into the brain.
<!-- END brain.md -->
