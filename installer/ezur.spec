# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir para ezur.

Un solo árbol de carpetas (`dist_exe/ezur/`), no un `.exe` que se descomprime en
%TEMP% en cada arranque: onedir arranca más rápido y es lo que menos falsos
positivos de antivirus levanta. El instalador de Inno Setup empaqueta este árbol
tal cual.

Lo que entra:
* `desktop.py` como punto de entrada (ventana + servidor local).
* `frontend/dist` — la UI compilada, que `server.main` busca relativa al CWD.
* `profiles/{demo,okx}/config.json` y los CSV de `data/` para que el
  Laboratorio y los perfiles funcionen recién instalado.

Lo que no entra: el motor ni la lógica de trading se tocan; se importan igual
que en `run.py`.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # installer/ -> raíz del repo

# Nada aquí: en onedir, PyInstaller 6 deja los `datas` en `_internal/`, y el
# servidor resuelve `frontend/dist`, `data/` y `profiles/` desde el directorio de
# trabajo (la carpeta del .exe). Lo que la app lee del disco se copia al lado del
# ejecutable en el paso final, no dentro de `_internal/`.
DATAS: list[tuple[str, str]] = []

HIDDEN = [
    "server.main",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr_loader",
    "pythonnet",
]

# Otros backends de pywebview (arrastra Qt aunque uses WebView2) y lo que solo
# usa el desarrollo: nada de esto se importa en tiempo de ejecución.
EXCLUDES = [
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "cefpython3",
    "gi",
    "matplotlib",
    "pytest",
    "_pytest",
    "httpx",
    "httpcore",
]

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ezur",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "installer" / "ezur.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ezur",
)


# --- lo que la app abre en tiempo de ejecución, junto al .exe ---------------
import shutil

OUT = Path(DISTPATH) / "ezur"
shutil.copytree(ROOT / "frontend" / "dist", OUT / "frontend" / "dist", dirs_exist_ok=True)
for profile in ("demo", "okx"):
    dest = OUT / "profiles" / profile
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "profiles" / profile / "config.json", dest / "config.json")
(OUT / "data").mkdir(parents=True, exist_ok=True)
for csv_name in ("BTC_1m.csv", "demo_bars.csv"):
    shutil.copy2(ROOT / "data" / csv_name, OUT / "data" / csv_name)

# Configuración por defecto del ejecutable: el perfil demo (estrategia
# `reference` sobre datos simulados). Sin esto, una instalación recién hecha
# arrancaría con `strategy.id = "null"` y Reanudar no tendría nada que evaluar.
shutil.copy2(ROOT / "profiles" / "demo" / "config.json", OUT / "data" / "config.json")
