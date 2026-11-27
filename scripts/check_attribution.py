#!/usr/bin/env python3
"""Rechaza mensajes de commit con `Co-Authored-By` de Codebuff.

Lo ejecuta el hook `.githooks/commit-msg` sobre el mensaje que se está
escribiendo y el job `attribution` de CI sobre los commits que entran en la
rama. La regla vive en AGENTS.md: el historial se limpió una vez y la
atribución no debe volver por accidente.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_TRAILER = re.compile(r"^\s*co-authored-by\s*:.*codebuff", re.IGNORECASE)


@dataclass(frozen=True)
class Offence:
    number: int
    line: str


def offending_lines(text: str) -> list[Offence]:
    """Líneas del mensaje que atribuyen el commit a Codebuff."""
    return [
        Offence(number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if _TRAILER.search(line)
    ]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def check_commits(revision_range: str) -> list[str]:
    """Problems for every commit in the range that carries the trailer."""
    problems: list[str] = []
    for sha in _git("rev-list", revision_range).split():
        message = _git("show", "-s", "--format=%B", sha)
        subject = _git("show", "-s", "--format=%s", sha).strip()
        for offence in offending_lines(message):
            problems.append(
                f"{sha[:12]} {subject}\n  línea {offence.number}: {offence.line}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--message-file",
        type=Path,
        help="mensaje de commit sin confirmar (hook commit-msg)",
    )
    source.add_argument(
        "--range",
        dest="revision_range",
        help="rango de git rev-list, por ejemplo origin/master..HEAD",
    )
    source.add_argument(
        "--rev",
        help="revisión cuyos ancestros se revisan, por ejemplo HEAD",
    )
    args = parser.parse_args(argv)

    try:
        if args.message_file is not None:
            text = args.message_file.read_text(encoding="utf-8", errors="replace")
            problems = [
                f"mensaje: línea {offence.number}: {offence.line}"
                for offence in offending_lines(text)
            ]
        else:
            problems = check_commits(args.revision_range or args.rev or "HEAD")
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if not problems:
        return 0

    print(
        f"ERROR: {len(problems)} atribución(es) a Codebuff en el mensaje:",
        file=sys.stderr,
    )
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "Quita el trailer Co-Authored-By de Codebuff "
        "(git commit --amend o git rebase -i) antes de continuar.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
