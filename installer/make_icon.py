"""Genera `installer/ezur.ico` con la geometría del logo de la app.

Misma placa redondeada y mismas tres barras que `frontend/src/components/Logo.tsx`,
medidas sobre el viewBox de 48 y dibujadas a la resolución de cada tamaño. Se
escriben los seis tamaños que Windows usa de verdad (16 en la barra de título,
256 en el explorador) como PNG dentro del contenedor ICO: así el icono de 16 px
no es una reducción del de 256, que es donde la E se cerraría.

    python installer/make_icon.py
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "installer" / "ezur.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]

ACCENT_TOP = "#5cf0e2"
ACCENT_BOTTOM = "#23c8ba"
CUT = "#070b11"

# Geometría del SVG (viewBox 48): placa 1.5..46.5 r=12, barras de 6.5.
PLATE = (1.5, 1.5, 46.5, 46.5)
RADIUS = 12.0
BARS = [
    (13.0, 11.0, 6.5, 26.0),
    (13.0, 11.0, 21.0, 6.5),
    (13.0, 20.75, 17.0, 6.5),
    (13.0, 30.5, 23.0, 6.5),
]


def render(size: int) -> Image.Image:
    scale = size / 48.0
    plate = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Degradado vertical del acento, recortado por la placa redondeada.
    gradient = ImageOps.colorize(
        Image.linear_gradient("L").resize((size, size)),
        black=ACCENT_BOTTOM,
        white=ACCENT_TOP,
    ).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [
            round(PLATE[0] * scale),
            round(PLATE[1] * scale),
            round(PLATE[2] * scale) - 1,
            round(PLATE[3] * scale) - 1,
        ],
        radius=RADIUS * scale,
        fill=255,
    )
    plate.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(plate)
    for x, y, w, h in BARS:
        draw.rectangle(
            [
                round(x * scale),
                round(y * scale),
                round((x + w) * scale) - 1,
                round((y + h) * scale) - 1,
            ],
            fill=CUT,
        )
    return plate


def write_ico(path: Path, frames: list[Image.Image]) -> None:
    """Contenedor ICO con un PNG por tamaño (Vista y posteriores)."""
    blobs: list[bytes] = []
    for frame in frames:
        buffer = BytesIO()
        frame.save(buffer, format="PNG", optimize=True)
        blobs.append(buffer.getvalue())

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries = bytearray()
    for frame, blob in zip(frames, blobs):
        side = frame.width
        entries += struct.pack(
            "<BBBBHHII",
            0 if side >= 256 else side,  # 0 significa 256
            0 if side >= 256 else side,
            0,
            0,
            1,
            32,
            len(blob),
            offset,
        )
        offset += len(blob)
    path.write_bytes(header + bytes(entries) + b"".join(blobs))


def main() -> None:
    frames = [render(size) for size in SIZES]
    write_ico(OUT, frames)
    print(f"{OUT} · {OUT.stat().st_size} bytes · {len(SIZES)} tamaños {SIZES}")


if __name__ == "__main__":
    main()
