"""Load label rows and build the per-round training mix.

Round N trains on this round's fresh gym pages, this round's attacker pages,
misses from the previous round's dev eval, and a small replay of older dev
misses. ``copycat_domain`` and ``listing_injection`` are dropped. Frozen test
ids are dropped. The dev split is not trained on.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from guardtrain.prompts import build_messages, dump_output, gold_object, truncate_to_tokens
from guardtrain.schema import (
    ATTACK_ALIASES,
    ATTACK_TYPES,
    FIELD_ALIASES,
    FORBIDDEN_SPLITS,
    FORBIDDEN_TRAIN_PAGE_SETS,
    HELD_OUT_ATTACKS,
    VERDICT_ALIASES,
    ContractError,
    LabelRow,
)


def _first(raw: dict, names: Sequence[str]):
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return None


def _norm_attack(value: object) -> str:
    text = "" if value is None else str(value).strip().lower()
    return ATTACK_ALIASES.get(text, text)


def _norm_verdict(value: object) -> str:
    text = "" if value is None else str(value).strip().lower()
    return VERDICT_ALIASES.get(text, text)


def row_from_obj(raw: dict) -> LabelRow:
    page_id = _first(raw, FIELD_ALIASES["page_id"])
    page_text = _first(raw, FIELD_ALIASES["page_text"])
    known = {name for names in FIELD_ALIASES.values() for name in names}
    extra = {k: v for k, v in raw.items() if k not in known}
    return LabelRow(
        page_id="" if page_id is None else str(page_id),
        store=str(_first(raw, FIELD_ALIASES["store"]) or ""),
        family=str(_first(raw, FIELD_ALIASES["family"]) or "").strip().lower(),
        attack_type=_norm_attack(_first(raw, FIELD_ALIASES["attack_type"])),
        verdict=_norm_verdict(_first(raw, FIELD_ALIASES["verdict"])),
        selector=str(_first(raw, FIELD_ALIASES["selector"]) or ""),
        bbox=_first(raw, FIELD_ALIASES["bbox"]),
        evidence_text=str(_first(raw, FIELD_ALIASES["evidence_text"]) or ""),
        instruction=str(_first(raw, FIELD_ALIASES["instruction"]) or ""),
        source=str(_first(raw, FIELD_ALIASES["source"]) or ""),
        split=str(_first(raw, FIELD_ALIASES["split"]) or "").strip().lower(),
        page_text="" if page_text is None else str(page_text),
        page_set=str(_first(raw, FIELD_ALIASES["page_set"]) or "").strip().lower(),
        model_output=str(_first(raw, FIELD_ALIASES["model_output"]) or ""),
        extra=extra,
    )


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path}:{line_no} is not JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ContractError(f"{path}:{line_no} must be a JSON object")
        rows.append(obj)
    return rows


def load_label_file(path: Path) -> list[LabelRow]:
    return [row_from_obj(obj) for obj in read_jsonl(path)]


def load_labels(path: Path) -> list[LabelRow]:
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.jsonl"))
        if not files:
            raise ContractError(f"No JSONL files in {path}")
        rows: list[LabelRow] = []
        for file in files:
            rows.extend(load_label_file(file))
        return rows
    if not path.is_file():
        raise ContractError(f"Label file not found: {path}")
    return load_label_file(path)


def load_id_list(path: Path) -> list[str]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line.split()[0])
    return ids


def discover_frozen_ids(root: Path, extra_files: Iterable[Path] = ()) -> set[str]:
    """Page ids that must never enter a training mix.

    Label JSONL files contribute ``page_id``. Id lists are only ``*.txt`` files
    that sit directly in the test-set directory (``slice100.txt``) plus any
    path passed in. ``data/testset/text/*.txt`` is page text, not an id list.
    """
    ids: set[str] = set()
    candidates = [
        root / "data" / "testset",
        root / "gym" / "testset",
        root / "gym" / "data" / "testset",
    ]
    files: list[Path] = list(extra_files)
    for cand in candidates:
        if cand.is_file():
            files.append(cand)
        elif cand.is_dir():
            files.extend(sorted(cand.glob("*.jsonl")))
            files.extend(sorted(cand.glob("*.txt")))
    seen: set[Path] = set()
    for file in files:
        file = Path(file)
        if file in seen or not file.is_file():
            continue
        seen.add(file)
        if file.suffix == ".txt":
            ids.update(load_id_list(file))
        elif file.suffix == ".jsonl":
            for row in load_label_file(file):
                if row.page_id:
                    ids.add(row.page_id)
                legacy = (row.extra or {}).get("legacy_page_id")
                if legacy:
                    ids.add(str(legacy))
    return ids


def default_pages_dir(labels: Path) -> Path:
    """Sibling ``text/`` directory. Gym writes ``data/testset/text`` and ``data/trainset/text``."""
    path = Path(labels)
    parent = path if path.is_dir() else path.parent
    return parent / "text"


def resolve_pages_dir(labels: Path, pages_dir: Path | None) -> Path:
    if pages_dir is not None:
        return Path(pages_dir)
    return default_pages_dir(labels)


def attach_page_text(rows: list[LabelRow], pages_dir: Path | None, *, required: bool = True) -> None:
    """Fill empty ``page_text`` from ``<pages_dir>/<page_id>.txt``.

    Rows that already carry text are left alone. When ``required`` is set, a
    row that still has no text is an error. Scoring those rows as empty pages
    would look like a real eval.
    """
    missing: list[str] = []
    pages = Path(pages_dir) if pages_dir is not None else None
    for row in rows:
        if (row.page_text or "").strip():
            continue
        found = False
        if pages is not None and row.page_id:
            for rel in (
                f"{row.page_id}.txt",
                f"{row.page_id}.html",
                f"{row.page_id}.md",
                f"{row.store}/{row.page_id}.txt" if row.store else "",
            ):
                if not rel:
                    continue
                path = pages / rel
                if path.is_file():
                    row.page_text = path.read_text(encoding="utf-8")
                    found = True
                    break
        if not found:
            missing.append(row.page_id or "<missing page_id>")
    if required and missing:
        shown = ", ".join(missing[:8])
        extra = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
        where = str(pages) if pages is not None else "<labels>/text"
        raise ContractError(
            f"Missing page text for {len(missing)} row(s). "
            f"Expected {where}/<page_id>.txt. Missing: {shown}{extra}"
        )


def _evidence_in_page(row: LabelRow, max_page_tokens: int) -> bool:
    evidence = (row.evidence_text or "").strip()
    if not evidence:
        return True
    page = truncate_to_tokens(row.page_text or "", max_page_tokens)
    return " ".join(evidence.split()).casefold() in " ".join(page.split()).casefold()


def training_skip_reason(row: LabelRow, test_ids: set[str], *, max_page_tokens: int) -> str | None:
    if not row.page_id:
        return "missing_page_id"
    if not (row.page_text or "").strip():
        return "missing_page_text"
    if row.attack_type in HELD_OUT_ATTACKS:
        return "held_out_attack"
    if row.page_set in FORBIDDEN_TRAIN_PAGE_SETS:
        return "forbidden_page_set"
    if row.split in FORBIDDEN_SPLITS:
        return "forbidden_split"
    if row.page_id in test_ids:
        return "frozen_test_id"
    if row.attack_type not in ATTACK_TYPES:
        return "unknown_attack_type"
    if row.verdict not in {"block", "pass"}:
        return "unknown_verdict"
    if row.verdict == "pass" and row.attack_type != "none":
        return "inconsistent_pass"
    if row.verdict == "block" and row.attack_type == "none":
        return "inconsistent_block"
    if row.family == "clean" and row.verdict != "pass":
        return "inconsistent_clean"
    if row.family in {"upsell", "scam"} and row.verdict != "block":
        return "inconsistent_family"
    if row.verdict == "block" and (row.evidence_text or "").strip() and not _evidence_in_page(row, max_page_tokens):
        return "evidence_not_in_page"
    return None


@dataclass
class AssembleStats:
    input_rows: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    by_attack: dict[str, int] = field(default_factory=dict)
    replay_cap: int = 0

    def as_dict(self) -> dict:
        return {
            "input_rows": self.input_rows,
            "kept": self.kept,
            "dropped": dict(self.dropped),
            "by_source": dict(self.by_source),
            "by_attack": dict(self.by_attack),
            "replay_cap": self.replay_cap,
        }


def _drop(stats: AssembleStats, reason: str) -> None:
    stats.dropped[reason] = stats.dropped.get(reason, 0) + 1


def filter_trainable(
    rows: Iterable[LabelRow],
    test_ids: set[str],
    *,
    max_page_tokens: int,
    mix_source: str,
) -> tuple[list[LabelRow], AssembleStats]:
    stats = AssembleStats()
    kept: list[LabelRow] = []
    for row in rows:
        stats.input_rows += 1
        reason = training_skip_reason(row, test_ids, max_page_tokens=max_page_tokens)
        if reason:
            _drop(stats, reason)
            continue
        row.mix_source = mix_source
        kept.append(row)
        stats.kept += 1
        stats.by_attack[row.attack_type] = stats.by_attack.get(row.attack_type, 0) + 1
    stats.by_source[mix_source] = len(kept)
    return kept, stats


def assert_miss_file_trainable(rows: list[LabelRow], test_ids: set[str] | None = None) -> None:
    """Misses used for the next round must be dev misses, never frozen test pages."""
    frozen = test_ids or set()
    for row in rows:
        if row.page_set in FORBIDDEN_TRAIN_PAGE_SETS:
            raise ContractError(
                "Refusing miss file tagged page_set="
                f"{row.page_set!r}. Mine misses on the dev split only, never the "
                "frozen test set or the 100-page slice."
            )
        if row.extra.get("not_for_training") is True:
            raise ContractError("Refusing miss file marked not_for_training.")
        if row.page_id and row.page_id in frozen:
            raise ContractError(
                f"Refusing miss {row.page_id}: it is in the frozen test set. "
                "Misses for the next round come only from the dev eval."
            )


def replay_sample(
    rows: list[LabelRow],
    fraction: float,
    seed: int,
    exclude_ids: set[str],
) -> list[LabelRow]:
    if fraction <= 0 or not rows:
        return []
    pool = [row for row in rows if row.page_id not in exclude_ids]
    grouped: dict[str, list[LabelRow]] = defaultdict(list)
    for row in pool:
        grouped[row.attack_type].append(row)
    rng = random.Random(seed)
    picked: list[LabelRow] = []
    for group in grouped.values():
        n = min(len(group), max(1, int(math.ceil(len(group) * fraction))))
        chosen = rng.sample(group, n)
        for row in chosen:
            clone = row_from_obj(row.as_dict())
            clone.mix_source = "replay"
            clone.model_output = row.model_output
            picked.append(clone)
    return picked


def partition_dev(rows: list[LabelRow]) -> tuple[list[LabelRow], list[LabelRow]]:
    """A dev row never enters the training mix, even if it was concatenated into the train file."""
    train: list[LabelRow] = []
    dev: list[LabelRow] = []
    for row in rows:
        if row.split == "dev" or row.page_set == "dev":
            dev.append(row)
        else:
            train.append(row)
    return train, dev


def assemble_round(
    *,
    round_index: int,
    round0_rows: list[LabelRow],
    previous_misses: list[LabelRow],
    older_misses: list[LabelRow],
    test_ids: set[str],
    replay_fraction: float,
    seed: int,
    max_page_tokens: int,
    attacker_rows: list[LabelRow] | None = None,
    replay_cap: int | None = None,
) -> tuple[list[LabelRow], AssembleStats]:
    """Fresh train pages, this round's attacker pages, previous dev misses, and a small replay.

    ``round0_rows`` is this round's freshly generated train split, not a reused round-0 file.
    Dev rows are rejected before this function. Replay is capped so it stays smaller than
    the fresh pages (at least 8, otherwise one fifth of the fresh rows that survived filters).
    """
    if round_index < 0:
        raise ContractError("--round must be >= 0")
    attacker_rows = list(attacker_rows or [])
    if round_index == 0 and (previous_misses or older_misses):
        raise ContractError("Round 0 does not take misses or replay. Those start at round 1.")
    if previous_misses:
        assert_miss_file_trainable(previous_misses, test_ids)
    if older_misses:
        assert_miss_file_trainable(older_misses, test_ids)

    stats = AssembleStats(
        input_rows=len(round0_rows) + len(attacker_rows) + len(previous_misses) + len(older_misses)
    )
    base, base_stats = filter_trainable(
        round0_rows, test_ids, max_page_tokens=max_page_tokens, mix_source="train"
    )
    attacked, attack_stats = filter_trainable(
        attacker_rows, test_ids, max_page_tokens=max_page_tokens, mix_source="attacker"
    )
    misses, miss_stats = filter_trainable(
        previous_misses, test_ids, max_page_tokens=max_page_tokens, mix_source="miss"
    )
    for part in (base_stats, attack_stats, miss_stats):
        for reason, count in part.dropped.items():
            stats.dropped[reason] = stats.dropped.get(reason, 0) + count

    by_id: dict[str, LabelRow] = {}
    for row in base:
        by_id[row.page_id] = row
    for row in attacked:
        by_id[row.page_id] = row
    for row in misses:
        by_id[row.page_id] = row  # a dev miss replaces the fresh copy of that page

    fresh_kept = len(base) + len(attacked)
    cap = replay_cap if replay_cap is not None else max(8, fresh_kept // 5)
    stats.replay_cap = cap
    exclude = set(by_id)
    replay = replay_sample(older_misses, replay_fraction, seed, exclude)
    replay, replay_stats = filter_trainable(
        replay, test_ids, max_page_tokens=max_page_tokens, mix_source="replay"
    )
    for reason, count in replay_stats.dropped.items():
        stats.dropped[reason] = stats.dropped.get(reason, 0) + count
    if len(replay) > cap:
        replay = _trim_replay(replay, cap, seed)
    for row in replay:
        if row.page_id not in by_id:
            by_id[row.page_id] = row

    mixed = list(by_id.values())
    mixed.sort(key=lambda row: row.page_id)
    stats.kept = len(mixed)
    stats.by_source = {"train": 0, "attacker": 0, "miss": 0, "replay": 0}
    stats.by_attack = {}
    for row in mixed:
        stats.by_source[row.mix_source] = stats.by_source.get(row.mix_source, 0) + 1
        stats.by_attack[row.attack_type] = stats.by_attack.get(row.attack_type, 0) + 1
    if not mixed:
        raise ContractError("Training mix is empty after hold-out and test-set filters.")
    return mixed, stats


def _trim_replay(rows: list[LabelRow], cap: int, seed: int) -> list[LabelRow]:
    """Keep a stratified subset. Used only when the replay sample is still too large."""
    if cap < 1:
        return []
    grouped: dict[str, list[LabelRow]] = defaultdict(list)
    for row in rows:
        grouped[row.attack_type].append(row)
    rng = random.Random(seed + 17)
    ordered_groups = [grouped[key] for key in sorted(grouped)]
    for group in ordered_groups:
        rng.shuffle(group)
    picked: list[LabelRow] = []
    while len(picked) < cap and any(ordered_groups):
        for group in ordered_groups:
            if group and len(picked) < cap:
                picked.append(group.pop())
    picked.sort(key=lambda row: row.page_id)
    return picked


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sft_records(
    rows: Sequence[LabelRow],
    *,
    max_page_tokens: int,
    system_in_user: bool,
    hide_held_out_labels: bool,
) -> list[dict]:
    records = []
    for row in rows:
        distilled = ""
        if row.extra:
            distilled = str(row.extra.get("distilled_target") or "")
        messages = build_messages(
            row,
            max_page_tokens=max_page_tokens,
            system_in_user=system_in_user,
            hide_held_out_labels=hide_held_out_labels,
            include_assistant=True,
            assistant_text=distilled or None,
        )
        records.append({"messages": messages})
    return records


def dpo_records(
    rows: Sequence[LabelRow],
    *,
    max_page_tokens: int,
    system_in_user: bool,
    hide_held_out_labels: bool,
) -> list[dict]:
    """Preference pairs from real misses. Round-0 rows have no rejected output."""
    records = []
    for row in rows:
        if row.mix_source not in {"miss", "replay"}:
            continue
        rejected = (row.model_output or "").strip()
        if not rejected:
            continue
        chosen = dump_output(gold_object(row))
        if rejected == chosen:
            continue
        prompt = build_messages(
            row,
            max_page_tokens=max_page_tokens,
            system_in_user=system_in_user,
            hide_held_out_labels=hide_held_out_labels,
            include_assistant=False,
        )
        records.append(
            {
                "prompt": prompt,
                "chosen": [{"role": "assistant", "content": chosen}],
                "rejected": [{"role": "assistant", "content": rejected}],
            }
        )
    return records


def dev_preference_rows(dev_rows: Sequence[LabelRow], metrics: dict) -> list[LabelRow]:
    """DPO pairs from this round's dev false blocks and dev misses. Never test pages."""
    by_id = {row.page_id: row for row in dev_rows}
    picked: list[LabelRow] = []
    seen: set[str] = set()
    for page in metrics.get("pages") or []:
        page_id = str(page.get("page_id") or "")
        row = by_id.get(page_id)
        if row is None or page_id in seen:
            continue
        if row.page_set in FORBIDDEN_TRAIN_PAGE_SETS or row.split in FORBIDDEN_SPLITS:
            continue
        false_block = row.family == "clean" and page.get("verdict") == "block"
        if not false_block and not page.get("miss"):
            continue
        seen.add(page_id)
        clone = row_from_obj(row.as_dict())
        clone.mix_source = "miss"
        clone.page_set = "dev"
        clone.split = "dev"
        raw = str(page.get("raw_output") or "").strip()
        if not raw:
            raw = json.dumps(
                {
                    "verdict": page.get("verdict") or "pass",
                    "attack_type": page.get("attack_type") or "none",
                    "evidence": page.get("evidence") or "",
                    "instruction": page.get("instruction") or "",
                },
                ensure_ascii=False,
            )
        clone.model_output = raw
        picked.append(clone)
    return picked


def load_previous_miss_files(paths: Sequence[Path], test_ids: set[str] | None = None) -> list[LabelRow]:
    rows: list[LabelRow] = []
    for path in paths:
        file_rows = load_labels(path)
        assert_miss_file_trainable(file_rows, test_ids)
        rows.extend(file_rows)
    return rows
