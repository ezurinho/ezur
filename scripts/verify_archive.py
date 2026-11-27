"""Verifica que las cifras publicadas se siguen reproduciendo.

El producto del laboratorio es el archivo: si un número deriva en silencio —otra
versión de pandas, un panel regenerado, un script editado—, el informe de cierre
se podre y nadie lo nota. Este comando vuelve a medir lo barato y compara con lo
publicado, con tolerancias explícitas.

Comprueba:
1. los hashes de los dos paneles contra su `freeze.json`;
2. que el cribado sobre el panel congelado dé 80,51 pb;
3. que las seis familias de la convención de esperanza sigan con el mismo veredicto;
4. que la dispersión de 2026 siga en 30,25 pb en cash y 189,49 en 8 h;
5. que la cadena del ledger de ensayos esté intacta;
6. que cada cifra publicada siga coincidiendo con su JSON y con su unidad
   (patas o compuesto), incluidas las cabeceras de tabla.

Uso:
    python scripts/verify_archive.py
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASA' if ok else 'FALLA'}  {name}: {detail}")
    return ok


def check_panel(folder: Path) -> bool:
    freeze = json.loads((folder / "freeze.json").read_text(encoding="utf-8"))
    funding = folder / "funding_daily.csv"
    perp = folder / "perp_daily.csv"
    ok_funding = sha(funding) == freeze["funding_sha256"]
    ok_perp = sha(perp) == freeze["perp_sha256"]
    return check(f"hashes {folder.name}", ok_funding and ok_perp,
                 f"funding {'ok' if ok_funding else 'NO'} · "
                 f"velas {'ok' if ok_perp else 'NO'}")


def run_json(script: str, json_path: Path, *args: str) -> dict | None:
    command = [PY, str(ROOT / "scripts" / script), "--json", str(json_path), *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if not json_path.is_file():
        print(f"  salida de {script}: {result.stdout[-300:]} {result.stderr[-300:]}")
        return None
    return json.loads(json_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cifras publicadas contra su fuente
# ---------------------------------------------------------------------------

# El valor no se escribe aquí: se lee del JSON en cada ejecución. Si el panel se
# regenera o el motor cambia, la cifra publicada deja de coincidir y la
# verificación falla; un número copiado a mano caduca en silencio, que es lo que
# pasó con el neto de patas comparado contra uno compuesto.
FIGURAS = (
    ("H5 · majors", "data/h10/validation_h5.json", ("majors", "A"),
     ("docs/MEDICION-COSTE.md", "docs/ARCHIVO-H5.md")),
    ("H10 · quintil sin filtro", "data/h10/validation_h5.json",
     ("h10_persistente", "quintil sin filtro"), ("docs/MEDICION-COSTE.md",)),
    ("H10 · quintil con filtro 5M", "data/h10/validation_h5.json",
     ("h10_persistente", "quintil con filtro"), ("docs/MEDICION-COSTE.md",)),
    ("H10 · k=4 con filtro 5M", "data/h10/validation_h5.json",
     ("h10_persistente", "k=4 con filtro"), ("docs/MEDICION-COSTE.md",)),
)

CUE_COMPUESTO = ("compuesto", "compuesta", "capitaliz")
CUE_PATAS = ("patas", "aritmética", "aritmetica")


def _resolve(node, path):
    """Baja por el JSON admitiendo claves con sufijo («A · convenciones…»)."""
    for key in path:
        if key in node:
            node = node[key]
            continue
        matches = [k for k in node if k == key or k.startswith(key + " ")]
        if len(matches) != 1:
            raise KeyError(f"{key!r}: {len(matches)} claves coinciden en {list(node)[:6]}")
        node = node[matches[0]]
    return node


def _es(value: float, decimals: int) -> str:
    """Formato de los docs: 6.086,46."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _forms(value: float) -> list[str]:
    """Las formas en que un doc puede escribir la misma cifra."""
    rounded, truncated = round(value), int(value)
    forms = [_es(value, 2), _es(value, 1), _es(float(rounded), 0)]
    if truncated != rounded:
        forms.append(_es(float(truncated), 0))
    return list(dict.fromkeys(forms))


def _hits(text: str, form: str):
    """Busca la cifra sin confundirla con un prefijo de otra mayor."""
    decimals = len(form.split(",")[1]) if "," in form else 0
    tail = r"(?![\d.,])" if decimals == 0 else r"(?!\d)"
    # Lista y no iterador: `any(finditer(...))` sería siempre True, porque un
    # iterador vacío sigue siendo un objeto verdadero.
    return list(re.finditer(r"(?<![\d.,])" + re.escape(form) + tail, text))


def _number(cell: str) -> float | None:
    """Convierte «+24.589,97 USD» en 24589.97."""
    raw = re.sub(r"[^\d,.+-]", "", cell)
    if not any(ch.isdigit() for ch in raw):
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1 or re.search(r"\.\d{3}$", raw):
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _figures_report() -> tuple[int, list[str]]:
    docs = {path: path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "docs").glob("*.md"))}
    figures = []
    for name, source, path, must in FIGURAS:
        node = _resolve(json.loads((ROOT / source).read_text(encoding="utf-8")), path)
        figures.append((name, float(node["neto"]), float(node["neto_compuesto"]), must))

    issues: list[str] = []
    inspected = 0
    seen: set[str] = set()

    # 1. Presencia: la cifra compuesta del JSON tiene que seguir escrita donde toca.
    for name, _patas, comp, must in figures:
        for doc in must:
            text = docs.get(ROOT / doc)
            if text is None:
                issues.append(f"{doc}: falta el documento")
            elif not any(_hits(text, form) for form in _forms(comp)):
                issues.append(f"{doc}: no aparece {_es(comp, 2)} de {name}"
                              " (¿cifra desactualizada?)")

    # 2. Unidad en prosa, por línea: si la línea cita las dos cifras de la misma
    #    familia es explícita («6.086,46 compuesto, patas 6.029,43») y no se
    #    toca. Si sólo cita la de patas y la llama compuesta, o le pone «neto» sin
    #    apellido, es el error que se coló y sí se señala.
    for doc, text in docs.items():
        rel = doc.relative_to(ROOT).as_posix()
        for number, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            mentions = 0
            for name, patas, comp, _must in figures:
                has_patas = any(_hits(line, form) for form in _forms(patas))
                has_comp = any(_hits(line, form) for form in _forms(comp))
                if not (has_patas or has_comp):
                    continue
                mentions += 1
                seen.add(name)
                if has_patas and has_comp or abs(patas - comp) < 0.011:
                    continue
                cue_patas = any(c in low for c in CUE_PATAS)
                cue_comp = any(c in low for c in CUE_COMPUESTO)
                if has_patas and cue_comp and not cue_patas:
                    issues.append(f"{rel}:{number}: {_es(patas, 2)} es patas de {name}"
                                  " y la línea lo llama compuesto")
                elif has_patas and not cue_patas and "neto" in low:
                    issues.append(f"{rel}:{number}: {_es(patas, 2)} es patas de {name}"
                                  " y la línea dice «neto» sin unidad")
            inspected += mentions

    # 3. Cabeceras: «Neto» sin apellido significa compuesto en este laboratorio.
    #    Una columna así con valores de patas es exactamente el error que se coló.
    rule = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
    for doc, text in docs.items():
        rel = doc.relative_to(ROOT).as_posix()
        lines = text.splitlines()
        i = 1
        while i < len(lines):
            if not (rule.match(lines[i]) and lines[i - 1].lstrip().startswith("|")):
                i += 1
                continue
            header = [c.strip() for c in lines[i - 1].strip().strip("|").split("|")]
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                row = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                for col, label in enumerate(header):
                    if label.lower() not in ("neto", "net") or col >= len(row):
                        continue
                    counted = _number(row[col])
                    if counted is None:
                        continue
                    for name, patas, comp, _must in figures:
                        if abs(counted - patas) < 0.011 and abs(patas - comp) > 0.011:
                            issues.append(f"{rel}:{j + 1}: columna «{label}» con "
                                          f"{row[col]}, que es patas de {name}")
                j += 1
            i = j

    return len(seen), issues


def check_figures() -> bool:
    try:
        inspected, issues = _figures_report()
    except (KeyError, FileNotFoundError) as error:
        return check("cifras publicadas", False, f"no se pudo leer la fuente: {error}")
    if inspected == 0:
        return check("cifras publicadas", False, "no se encontró ninguna cifra en los docs")
    detail = f"{inspected} familias cruzadas con el JSON"
    if issues:
        detail += " · " + "; ".join(issues[:4])
        if len(issues) > 4:
            detail += f" (+{len(issues) - 4} más)"
    return check("cifras publicadas", not issues, detail)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import pandas as pd  # sólo para reportar versiones

    print(f"entorno: python {sys.version.split()[0]} · pandas {pd.__version__}")
    ok = True
    ok &= check_panel(ROOT / "data" / "h10")
    ok &= check_panel(ROOT / "data" / "h10ext")
    ok &= check_figures()

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "screen.json"
        payload = run_json("screen_h10_dispersion.py", target)
        if payload is None:
            ok = False
        else:
            ok &= check("cribado H10", abs(payload["median_bp"] - 80.51) < 0.01,
                        f"{payload['median_bp']} pb (esperado 80,51)")

    convention = ROOT / "data" / "expectancy_convention.json"
    if convention.is_file():
        payload = json.loads(convention.read_text(encoding="utf-8"))
        # Nunca se da por bueno un campo ausente: un `None` que pasa el filtro
        # sería un falso positivo de la verificación.
        changed = payload.get("cambios")
        rows = payload.get("filas") or []
        ok &= check("convención de esperanza",
                    changed == 0 and len(rows) == 6,
                    f"{changed} de {len(rows)} veredictos cambian (esperado 0 de 6)")
    else:
        ok = check("convención de esperanza", False, "falta el JSON")

    dispersion = ROOT / "data" / "h10ext" / "dispersion.json"
    if dispersion.is_file():
        payload = json.loads(dispersion.read_text(encoding="utf-8"))
        year = payload["por_anio"]["2026"]
        ok &= check("dispersión 2026", abs(year["disp_cash_bp"] - 30.25) < 0.02
                    and abs(year["disp_eq8h_bp"] - 189.49) < 0.05,
                    f"cash {year['disp_cash_bp']} · 8h {year['disp_eq8h_bp']}")
    else:
        ok = check("dispersión 2026", False, "falta el JSON")

    ledger = ROOT / "data" / "lab_ledger.jsonl"
    if ledger.is_file():
        result = subprocess.run([PY, str(ROOT / "scripts" / "lab_ledger.py"), "--verify"],
                                cwd=ROOT, capture_output=True, text=True)
        ok &= check("ledger de ensayos", result.returncode == 0,
                    result.stdout.strip() or result.stderr.strip())
    else:
        ok = check("ledger de ensayos", False, "falta data/lab_ledger.jsonl")

    print("\n" + ("ARCHIVO VERIFICADO" if ok else "EL ARCHIVO NO REPRODUCE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
