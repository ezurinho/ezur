from __future__ import annotations

import pytest

from scripts.check_attribution import offending_lines


@pytest.mark.parametrize(
    "line",
    [
        "Co-Authored-By: Codebuff <noreply@codebuff.com>",
        "co-authored-by: codebuff-team <team@example.com>",
        "Generated with Codebuff",
        "🤖 Generated with Codebuff",
        "  Generated with Codebuff 🤖",
    ],
)
def test_rechaza_atribucion_de_codebuff(line: str) -> None:
    assert offending_lines(line)


def test_permite_un_asunto_que_menciona_codebuff() -> None:
    assert not offending_lines(
        "Rechaza en local los commits con Co-Authored-By de Codebuff."
    )


def test_permite_un_mensaje_normal() -> None:
    assert not offending_lines(
        "Cierra el hueco que dejaba pasar la línea de generación.\n\n"
        "El hook revisa el mensaje antes de crear el commit."
    )


def test_informa_la_linea_exacta() -> None:
    offences = offending_lines(
        "Asunto del cambio\n\n"
        "Cuerpo.\n"
        "Co-Authored-By: Codebuff <noreply@codebuff.com>\n"
        "Generated with Codebuff\n"
    )

    assert [(offence.number, offence.line) for offence in offences] == [
        (4, "Co-Authored-By: Codebuff <noreply@codebuff.com>"),
        (5, "Generated with Codebuff"),
    ]
