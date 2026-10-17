"""The runbook is the ordered list of commands for the paid machine."""

from __future__ import annotations

import re
from pathlib import Path

RUNBOOK = Path(__file__).resolve().parents[1] / "RUNBOOK.md"


def _commands(text: str) -> list[str]:
    """Join backslash-continued shell lines into one command each."""
    commands = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("python -m "):
            if current:
                commands.append(" ".join(current))
            current = [stripped.removesuffix("\\").strip()]
            if not stripped.endswith("\\"):
                commands.append(" ".join(current))
                current = []
        elif current and stripped.endswith("\\"):
            current.append(stripped.removesuffix("\\").strip())
        elif current and stripped:
            current.append(stripped)
            commands.append(" ".join(current))
            current = []
        elif current:
            commands.append(" ".join(current))
            current = []
    if current:
        commands.append(" ".join(current))
    return commands


def test_runbook_commands_are_ordered_and_secret_free() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert re.search(r"vk_[A-Za-z0-9]{8,}", text) is None
    assert "sk-ant-" not in text
    assert "Qwen/Qwen3-1.7B" in text
    assert "$50" in text
    assert "$2.50" in text
    assert "--min-replicas 0" in text
    assert "copycat_domain" in text
    assert "listing_injection" in text

    commands = _commands(text)
    names = []
    for command in commands:
        if command.startswith("python -m pytest"):
            names.append("pytest")
        elif command.startswith("python -m guardtrain "):
            names.append(command.split()[3])

    def first(name: str) -> int:
        assert name in names, name
        return names.index(name)

    order = [
        "pytest",
        "format",
        "round",
        "convert",
        "eval",
        "serve",
        "baseline-local",
        "baseline-gemini",
        "baseline-anthropic",
        "ledger",
    ]
    indexes = [first(name) for name in order]
    assert indexes == sorted(indexes)

    first_round = commands[names.index("round")]
    assert "--dry-run" in first_round
    live_rounds = [
        command
        for command in commands
        if command.startswith("python -m guardtrain round") and "--dry-run" not in command
    ]
    assert live_rounds
    assert commands.index(live_rounds[0]) > commands.index(
        next(command for command in commands if command.startswith("python -m guardtrain ledger show"))
    )

    convert = next(command for command in commands if command.startswith("python -m guardtrain convert"))
    assert "Qwen/Qwen3-4B" in convert
    evaluation = next(command for command in commands if command.startswith("python -m guardtrain eval"))
    assert "--backend mock" in evaluation
    gemini = next(command for command in commands if "baseline-gemini" in command)
    assert "--probe 5" in gemini
    pro = next(command for command in commands if "gemini-3.1-pro-preview" in command)
    assert "--probe" not in pro
    assert commands.index(pro) > commands.index(gemini)
    anthropic = next(command for command in commands if "baseline-anthropic" in command)
    assert "claude-sonnet-5-5" in anthropic

    veri = [
        "veri datasets check",
        "veri datasets upload",
        "veri jobs estimate",
        "veri jobs create",
        "veri jobs get",
        "veri jobs cancel",
        "veri jobs download",
    ]
    positions = [text.index(phrase) for phrase in veri]
    assert positions == sorted(positions)
