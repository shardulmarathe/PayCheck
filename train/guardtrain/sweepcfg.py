"""Load a sweep config. YAML for the example file, JSON when the suffix is .json.

The YAML reader covers the subset the example uses: nested maps and one-line
lists. A ``grid`` of learning_rate by lora_rank expands to one trial each.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

from guardtrain.schema import VERI_MAX_PARALLEL, ContractError


def _split_commas(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            current.append(char)
            continue
        if char == ",":
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _scalar(text: str):
    raw = text.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in _split_commas(inner)]
    if raw in {"true", "false"}:
        return raw == "true"
    if raw in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+(e-?\d+)?", raw, flags=re.IGNORECASE) or re.fullmatch(
        r"-?\d+e-?\d+", raw, flags=re.IGNORECASE
    ):
        return float(raw)
    return raw


def parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped:
            raise ContractError(f"Sweep YAML line is not a key: {stripped}")
        key, _, rest = stripped.partition(":")
        key = key.strip()
        value = rest.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value)
    return root


def assert_private_huggingface(config: dict) -> None:
    """A huggingface block, when present, must stay private and merged.

    The renderer writes that block even when the sweep file omits it. A file
    that asks for a public repo is refused before any job is created.
    """
    block = config.get("huggingface")
    if not block:
        return
    if not isinstance(block, dict):
        raise ContractError("huggingface must be a mapping with private: true.")
    private = block.get("private", True)
    artifact = block.get("artifact", "merged")
    if private is not True:
        raise ContractError(
            "Sweep huggingface.private must be true. A public repo is refused."
        )
    if artifact not in {None, "merged"}:
        raise ContractError('Sweep huggingface.artifact must be "merged".')


def load_sweep_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError:
            payload = parse_simple_yaml(text)
        else:
            payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ContractError(f"Sweep config {path} must be a mapping.")
    return payload


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-").lower()
    return cleaned or "trial"


def _trial_name(item: dict) -> str:
    lr = item.get("learning_rate")
    rank = item.get("lora_rank")
    lr_text = f"{float(lr):.0e}".replace("+", "").replace(".", "")
    return _safe_name(f"lr{lr_text}-r{int(rank)}")


def _normalize_trial(item: dict) -> dict:
    if "learning_rate" not in item or "lora_rank" not in item:
        raise ContractError("Each sweep trial needs learning_rate and lora_rank.")
    rank = int(item["lora_rank"])
    alpha = int(item["lora_alpha"]) if item.get("lora_alpha") is not None else rank * 2
    name = _safe_name(str(item.get("name") or _trial_name(item)))
    return {
        "name": name,
        "learning_rate": float(item["learning_rate"]),
        "lora_rank": rank,
        "lora_alpha": alpha,
    }


def expand_trials(config: dict) -> list[dict]:
    explicit = config.get("configs")
    if explicit:
        if not isinstance(explicit, list):
            raise ContractError("sweep configs must be a list.")
        trials = [_normalize_trial(item) for item in explicit]
    else:
        grid = config.get("grid") or {}
        if not isinstance(grid, dict) or not grid:
            raise ContractError("Sweep config needs configs or a grid of learning_rate and lora_rank.")
        keys = list(grid)
        columns = []
        for key in keys:
            value = grid[key]
            columns.append(value if isinstance(value, list) else [value])
        trials = []
        for combo in itertools.product(*columns):
            item = {key: combo[index] for index, key in enumerate(keys)}
            trials.append(_normalize_trial(item))
    if not trials:
        raise ContractError("Sweep config expanded to zero trials.")
    names = [trial["name"] for trial in trials]
    if len(names) != len(set(names)):
        raise ContractError(f"Sweep trial names must be unique, got {names}.")
    return trials


def parallel_limit(config: dict) -> int:
    requested = int(config.get("max_parallel") or VERI_MAX_PARALLEL)
    if requested < 1:
        raise ContractError("max_parallel must be at least 1.")
    return min(VERI_MAX_PARALLEL, requested)
