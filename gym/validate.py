"""JSON Schema checks plus taxonomy rules the schema cannot express cleanly."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import jsonschema

from gym.paths import schema_dir
from gym.taxonomy import FAMILY, family_of, verdict_of

_ID_SELECTOR = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")


@lru_cache(maxsize=8)
def load_schema(name: str) -> dict:
    path = schema_dir() / name
    return json.loads(path.read_text(encoding="utf-8"))


def _fail(spec: dict, message: str) -> None:
    page_id = spec.get("page_id", "?")
    raise ValueError(f"{page_id}: {message}")


def validate_spec(spec: dict) -> None:
    jsonschema.validate(spec, load_schema("trick_spec.json"))
    trick = spec["trick"]
    attack = trick["attack_type"]
    if trick["family"] != family_of(attack):
        _fail(spec, f"family {trick['family']!r} does not match {attack}")
    if trick["verdict"] != verdict_of(attack):
        _fail(spec, f"verdict {trick['verdict']!r} does not match {attack}")
    if attack == "none":
        if trick["evidence_text"] or trick["instruction"] or trick["selector"]:
            _fail(spec, "clean pages have empty evidence, instruction, and selector")
        if trick["family"] != "clean":
            _fail(spec, "clean family required")
        return
    if not trick["evidence_text"] or not trick["instruction"]:
        _fail(spec, "block pages need evidence_text and instruction")
    if not _ID_SELECTOR.fullmatch(trick["selector"]):
        _fail(spec, "selector must be a simple CSS id, like #trick")
    if attack in FAMILY and trick["family"] not in {"upsell", "scam"}:
        _fail(spec, "block pages are upsell or scam")


def validate_label(row: dict) -> None:
    jsonschema.validate(row, load_schema("label.json"))
    if row["family"] != family_of(row["attack_type"]):
        raise ValueError(f"{row['page_id']}: family mismatch")
    if row["verdict"] != verdict_of(row["attack_type"]):
        raise ValueError(f"{row['page_id']}: verdict mismatch")
    if row["verdict"] == "pass":
        if row["bbox"] is not None or row["selector"] or row["evidence_text"] or row["instruction"]:
            raise ValueError(f"{row['page_id']}: pass rows have null bbox and empty trick fields")
    else:
        if not isinstance(row["bbox"], list) or len(row["bbox"]) != 4:
            raise ValueError(f"{row['page_id']}: block rows need a bbox")
        if not row["selector"] or not row["evidence_text"] or not row["instruction"]:
            raise ValueError(f"{row['page_id']}: block rows need selector, evidence, and instruction")


def validate_guard_output(payload: dict) -> None:
    jsonschema.validate(payload, load_schema("guard_output.json"))
    if payload["verdict"] != verdict_of(payload["attack_type"]):
        raise ValueError("guard verdict does not match attack_type")
    if payload["verdict"] == "pass":
        if payload["evidence"] or payload["instruction"]:
            raise ValueError("pass output has empty evidence and instruction")
    elif not payload["evidence"] or not payload["instruction"]:
        raise ValueError("block output needs evidence and instruction")


def selector_id(selector: str) -> str:
    if not _ID_SELECTOR.fullmatch(selector):
        raise ValueError(f"not an id selector: {selector!r}")
    return selector[1:]


def guard_from_label(row: dict) -> dict[str, str]:
    """The label fields the guard is trained to emit."""
    return {
        "verdict": row["verdict"],
        "attack_type": row["attack_type"],
        "evidence": row["evidence_text"],
        "instruction": row["instruction"],
    }
