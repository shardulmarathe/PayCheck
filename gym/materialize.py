"""Write HTML, extracted text, specs, and JSONL labels for a list of specs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from gym.browser import Browser
from gym.render import page_url, render_html
from gym.taxonomy import VIEWPORT
from gym.validate import validate_label, validate_spec

LABEL_KEYS = (
    "page_id",
    "store",
    "family",
    "attack_type",
    "verdict",
    "selector",
    "bbox",
    "evidence_text",
    "instruction",
    "source",
    "split",
)


def dump_label(row: dict) -> str:
    ordered = {key: row[key] for key in LABEL_KEYS}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def dump_spec(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def prepare_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    (path / "html").mkdir(parents=True)
    (path / "text").mkdir(parents=True)
    (path / "specs").mkdir(parents=True)


def materialize(specs: list[dict], out_dir: Path) -> list[dict]:
    prepare_dir(out_dir)
    labels: list[dict] = []
    with Browser(VIEWPORT) as browser:
        font_checked = False
        for spec in specs:
            validate_spec(spec)
            html = render_html(spec, check=False)
            url = page_url(spec)
            browser.open_html(html, url)
            if not font_checked:
                family = browser.font_family()
                if "Liberation Sans" not in family:
                    raise RuntimeError(
                        "Liberation Sans is not the computed body font "
                        f"({family}). Install fonts-liberation before building the test set."
                    )
                font_checked = True
            trick = spec["trick"]
            evidence = trick["evidence_text"]
            bbox = None
            if trick["selector"]:
                got = browser.text_content(trick["selector"])
                if got != evidence:
                    raise RuntimeError(
                        f"{spec['page_id']}: #trick text {got!r} != evidence {evidence!r}"
                    )
                bbox = browser.bbox(trick["selector"])
                if bbox is None:
                    raise RuntimeError(f"{spec['page_id']}: no bbox for {trick['selector']}")
            compact = browser.compact_text()
            if evidence and evidence not in compact:
                raise RuntimeError(f"{spec['page_id']}: evidence missing from page reader output")
            label = {
                "page_id": spec["page_id"],
                "store": spec["store"]["id"],
                "family": trick["family"],
                "attack_type": trick["attack_type"],
                "verdict": trick["verdict"],
                "selector": trick["selector"],
                "bbox": bbox,
                "evidence_text": evidence,
                "instruction": trick["instruction"],
                "source": spec["source"],
                "split": spec["split"],
            }
            validate_label(label)
            page_id = spec["page_id"]
            (out_dir / "html" / f"{page_id}.html").write_text(html, encoding="utf-8")
            (out_dir / "text" / f"{page_id}.txt").write_text(compact, encoding="utf-8")
            (out_dir / "specs" / f"{page_id}.json").write_text(dump_spec(spec), encoding="utf-8")
            labels.append(label)
    payload = "\n".join(dump_label(row) for row in labels) + ("\n" if labels else "")
    (out_dir / "labels.jsonl").write_text(payload, encoding="utf-8")
    return labels
