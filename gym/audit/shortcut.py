"""Shortcut gate for a frozen split.

The gate runs on rendered HTML, not on a reviewer's impression. It fails when a
label is recoverable from an attribute value, from visible words outside the
trick evidence, from structural counts, or from the mean page length.

Attribute mirrors are render-time only. A value that shows up on one label is
copied onto one page of the other label as ``data-mirror``, inside the shared
off-screen wrapper. Ids are not copied onto a second element.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from gym.paths import shortcut_report_path
from gym.render import bind_echo, render_html, reset_echo
from gym.visible import page_view, visible_length, visible_text

TOKEN_AUC_MAX = 0.65
STRUCTURE_AUC_MAX = 0.70
LENGTH_GAP_MAX = 0.05


def _labels(specs: list[dict]) -> list[int]:
    return [0 if spec["trick"]["attack_type"] == "none" else 1 for spec in specs]


def separating_values(htmls: list[str], labels: list[int]) -> list[str]:
    """Attribute values that occur on exactly one of the two labels."""
    owners: dict[str, set[int]] = defaultdict(set)
    for html, label in zip(htmls, labels):
        for value in page_view(html).values:
            owners[value].add(label)
    return sorted(value for value, sides in owners.items() if len(sides) == 1)


def _echo_assignment(specs: list[dict], htmls: list[str]) -> dict[str, tuple[str, ...]]:
    labels = _labels(specs)
    owners: dict[str, set[int]] = defaultdict(set)
    for html, label in zip(htmls, labels):
        for value in page_view(html).values:
            owners[value].add(label)
    trick_only = sorted(value for value, sides in owners.items() if sides == {1})
    clean_only = sorted(value for value, sides in owners.items() if sides == {0})
    clean_ids = sorted(
        spec["page_id"] for spec, label in zip(specs, labels) if label == 0
    )
    trick_ids = sorted(
        spec["page_id"] for spec, label in zip(specs, labels) if label == 1
    )
    buckets: dict[str, list[str]] = {spec["page_id"]: [] for spec in specs}
    if clean_ids:
        for index, value in enumerate(trick_only):
            buckets[clean_ids[index % len(clean_ids)]].append(value)
    if trick_ids:
        for index, value in enumerate(clean_only):
            buckets[trick_ids[index % len(trick_ids)]].append(value)
    print(
        f"echo pages={len(specs)} trick_only={len(trick_only)} clean_only={len(clean_only)}",
        flush=True,
    )
    return {page_id: tuple(values) for page_id, values in buckets.items()}


def echoed_html(specs: list[dict]) -> list[str]:
    """Render twice: measure separating values, then mirror them onto the other label."""
    plain = [render_html(spec) for spec in specs]
    mapping = _echo_assignment(specs, plain)
    token = bind_echo(mapping)
    try:
        return [render_html(spec) for spec in specs]
    finally:
        reset_echo(token)


def attribute_probe(htmls: list[str], specs: list[dict]) -> dict:
    found = separating_values(htmls, _labels(specs))
    return {
        "pass": not found,
        "separating_count": len(found),
        "separating": found[:40],
        "note": (
            "Values of id, name, class (full string and tokens), data-*, for, and aria-*. "
            "Empty values are ignored. data-mirror copies a separating value onto one page "
            "of the other label."
        ),
    }


def _auc(model, features, labels: list[int]) -> float:
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score

    if len(set(labels)) < 2 or len(labels) < 10:
        return 0.5
    folds = 5 if min(labels.count(0), labels.count(1)) >= 5 else 2
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
    probabilities = cross_val_predict(model, features, labels, cv=cv, method="predict_proba")[:, 1]
    return round(float(roc_auc_score(labels, probabilities)), 4)


def token_probe(htmls: list[str], specs: list[dict]) -> dict:
    """Bag-of-words logistic regression on visible text with #offer-1 masked."""
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.linear_model import LogisticRegression

    texts = [visible_text(html, mask_evidence=True) for html in htmls]
    labels = _labels(specs)
    vector = CountVectorizer(min_df=2, ngram_range=(1, 1))
    features = vector.fit_transform(texts)
    if features.shape[1] == 0:
        auc = 0.5
    else:
        model = LogisticRegression(max_iter=400, solver="liblinear")
        auc = _auc(model, features, labels)
    return {
        "auc": auc,
        "pass": auc <= TOKEN_AUC_MAX,
        "threshold": TOKEN_AUC_MAX,
        "features": int(features.shape[1]),
        "note": (
            "CountVectorizer unigrams, min_df=2, logistic regression, "
            "stratified out-of-fold AUC. Visible text excludes script, style, "
            "off-screen copy, and the #offer-1 evidence element."
        ),
    }


def _structure_rows(htmls: list[str], specs: list[dict]) -> list[list[float]]:
    rows = []
    for html, spec in zip(htmls, specs):
        view = page_view(html, mask_evidence=False)
        rows.append(
            [
                float(visible_length(html)),
                float(view.inputs),
                float(view.modals),
                float(view.buttons),
                float(len(spec["page"]["cart"])),
                float(view.passwords),
                float(view.hidden),
            ]
        )
    return rows


def structure_probe(htmls: list[str], specs: list[dict]) -> dict:
    """Gradient-boosted trees on structural counts only."""
    from sklearn.ensemble import GradientBoostingClassifier

    labels = _labels(specs)
    rows = _structure_rows(htmls, specs)
    model = GradientBoostingClassifier(
        n_estimators=40,
        max_depth=2,
        learning_rate=0.1,
        random_state=0,
    )
    auc = _auc(model, rows, labels)
    return {
        "auc": auc,
        "pass": auc <= STRUCTURE_AUC_MAX,
        "threshold": STRUCTURE_AUC_MAX,
        "features": [
            "page_length",
            "n_inputs",
            "n_modals",
            "n_buttons",
            "n_cart_rows",
            "n_password",
            "n_hidden",
        ],
        "note": (
            "page_length is visible characters, including on-screen evidence and "
            "excluding off-screen text. n_cart_rows is the spec cart. n_hidden counts "
            "elements with the hidden attribute or class offscreen/parked."
        ),
    }


def length_probe(htmls: list[str], specs: list[dict]) -> dict:
    from gym.polish import length_gaps

    lengths = [visible_length(html) for html in htmls]
    kinds = length_gaps(specs, lengths)
    return {
        "pass": all(bool(row["pass"]) for row in kinds.values()) if kinds else True,
        "threshold": LENGTH_GAP_MAX,
        "kinds": kinds,
        "note": "relative gap is |mean trick - mean clean| / mean of those two means, per page kind.",
    }


def probe_set(specs: list[dict], htmls: list[str]) -> dict:
    print(f"probing {len(specs)} pages", flush=True)
    token = token_probe(htmls, specs)
    structure = structure_probe(htmls, specs)
    print(
        f"auc token={token['auc']} structure={structure['auc']}",
        flush=True,
    )
    return {
        "pages": len(specs),
        "attribute": attribute_probe(htmls, specs),
        "token": token,
        "structure": structure,
        "length": length_probe(htmls, specs),
    }


def hard_failures(report: dict) -> list[str]:
    """Attribute and length misses. AUC misses are disclosed rather than fatal."""
    failures = []
    for name, block in report["sets"].items():
        if not block["attribute"]["pass"]:
            sample = ", ".join(block["attribute"]["separating"][:8])
            failures.append(
                f"{name} attribute separating={block['attribute']['separating_count']} [{sample}]"
            )
        if not block["length"]["pass"]:
            gaps = {
                kind: row["relative_gap"]
                for kind, row in block["length"]["kinds"].items()
                if not row["pass"]
            }
            failures.append(f"{name} length gap {gaps}")
    return failures


def auc_misses(report: dict) -> list[str]:
    misses = []
    for name, block in report["sets"].items():
        if not block["token"]["pass"]:
            misses.append(f"{name} token auc {block['token']['auc']} > {TOKEN_AUC_MAX}")
        if not block["structure"]["pass"]:
            misses.append(
                f"{name} structure auc {block['structure']['auc']} > {STRUCTURE_AUC_MAX}"
            )
    return misses


def write_report(payload: dict, path: Path | None = None) -> Path:
    destination = path or shortcut_report_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination
