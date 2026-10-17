"""How round N starts from round N-1.

Round 1 starts from ``Qwen/Qwen3-4B-Instruct-2507``. Later SFT rounds start
from the previous round's private merged winner. Veri ``resume_from`` keeps
the previous method, dataset, and LoRA settings, so it is not used.

``--retrain-from-base`` is the fallback when a push did not land: retrain from
the public instruct model on every earlier train split plus the new pages.
DPO never starts from that public base. It starts from this round's merged
SFT winner.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from guardtrain.schema import PRIMARY_BASE_MODEL, ContractError, hf_repo_name


@dataclass
class Continuation:
    mode: str
    base_model: str
    reason: str
    cumulative_rounds: list[int]
    hf_repo: str


def model_id_from(value: str) -> str:
    text = (value or "").strip().rstrip("/")
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        parts = [part for part in text.split("/") if part]
        if len(parts) >= 2:
            return parts[-2] + "/" + parts[-1]
        return ""
    if "/" in text and " " not in text:
        return text
    return ""


def _winner_record(payload: dict) -> dict:
    winner_name = payload.get("winner")
    trials = payload.get("trials") or []
    chosen = None
    if winner_name and isinstance(trials, list):
        for trial in trials:
            if isinstance(trial, dict) and trial.get("name") == winner_name:
                chosen = trial
                break
    if chosen is None and isinstance(payload.get("trial"), dict):
        chosen = payload["trial"]
    repo = ""
    url = ""
    if isinstance(chosen, dict):
        repo = str(chosen.get("hf_repo") or "")
        url = str(chosen.get("hf_repo_url") or chosen.get("merged_base") or "")
    repo = repo or str(payload.get("hf_repo") or "")
    url = url or str(payload.get("hf_repo_url") or payload.get("merged_base") or "")
    pushed = bool(payload.get("hf_pushed") or (isinstance(chosen, dict) and chosen.get("hf_pushed")))
    return {"hf_repo": repo, "hf_repo_url": url, "hf_pushed": pushed or bool(url)}


def plan_continuation(
    runs: Path,
    round_index: int,
    requested_base: str,
    *,
    retrain_from_base: bool = False,
    trial: str = "sft",
) -> Continuation:
    """Base model for this round's SFT job, plus the private repo it will push."""
    repo = hf_repo_name(round_index, trial)
    if retrain_from_base:
        return Continuation(
            "retrain_cumulative",
            PRIMARY_BASE_MODEL,
            (
                "Fallback after a missed Hugging Face push. This round retrains from "
                "Qwen/Qwen3-4B-Instruct-2507 on every earlier train split plus this round's "
                "fresh pages aimed at the previous dev misses."
            ),
            list(range(max(0, round_index))),
            repo,
        )
    if round_index <= 1:
        return Continuation(
            "base",
            PRIMARY_BASE_MODEL,
            "Round 1 starts from Qwen/Qwen3-4B-Instruct-2507. Later rounds continue from the merged winner.",
            [],
            repo,
        )
    path = runs / "training" / f"round{round_index - 1}.json"
    record = {"hf_repo": "", "hf_repo_url": "", "hf_pushed": False}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            record = _winner_record(payload)
    merged = model_id_from(str(record.get("hf_repo_url") or "")) or model_id_from(
        str(record.get("hf_repo") or "")
    )
    if merged and record.get("hf_pushed"):
        return Continuation(
            "merged_base",
            merged,
            (
                "This round's SFT continues from the previous round's private merged winner. "
                "resume_from is not used, because a new round has a new dataset."
            ),
            [],
            repo,
        )
    if merged and not record.get("hf_pushed"):
        raise ContractError(
            f"Round {round_index - 1} named {merged} but did not record a completed private push. "
            "Pass --retrain-from-base to retrain from Qwen/Qwen3-4B-Instruct-2507 on the cumulative train pages."
        )
    raise ContractError(
        f"Round {round_index} needs the merged winner repo from round {round_index - 1}. "
        "Pass --retrain-from-base to retrain from Qwen/Qwen3-4B-Instruct-2507 on the cumulative train pages."
    )


def dpo_init(winner: dict, round_index: int, trial: str | None = None) -> tuple[str, str]:
    """Base model for DPO: this round's merged SFT winner, never the plain base."""
    name = trial or str(winner.get("name") or "sft")
    merged = (
        model_id_from(str(winner.get("hf_repo_url") or ""))
        or model_id_from(str(winner.get("hf_repo") or ""))
        or model_id_from(str(winner.get("merged_base") or ""))
        or hf_repo_name(round_index, name)
    )
    if merged == PRIMARY_BASE_MODEL or merged.startswith("Qwen/"):
        raise ContractError(
            "DPO starts from the current round's merged SFT winner, not the plain base."
        )
    if not merged.startswith("shardulmarathe/sureshop-guard-"):
        raise ContractError(
            f"DPO base {merged} is not a private sureshop-guard repo. "
            "Refusing to start DPO from anything except the merged SFT winner."
        )
    return merged, "merged"
