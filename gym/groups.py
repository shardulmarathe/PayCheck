"""Group ids for train/dev splits.

A group is one template or near-duplicate family. The dev split takes whole
groups, so a family never sits in both train and dev. Attacker specs set
``group_id`` themselves. Gym trick pages use the template, the store, and the
seed family. Clean pages use the store plus the template: page kind, layout,
and which honest control the page shows.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Callable, TypeVar

T = TypeVar("T")


def honest_feature_name(spec: dict) -> str:
    """Which honest control a clean page shows. Plain pages are their own template."""
    page = spec.get("page") or {}
    offers = page.get("offers") or {}
    if isinstance(offers, dict) and offers.get("checkbox"):
        return "checkbox"
    if isinstance(offers, dict) and offers.get("modal"):
        return "popup"
    if page.get("fees"):
        return "fee"
    if isinstance(offers, dict) and offers.get("was_cents"):
        return "strike"
    if isinstance(offers, dict) and offers.get("radios"):
        return "radio"
    return "plain"


def clean_template(spec: dict) -> str:
    """Store plus template. Two clean pages that share this are near-copies."""
    page = spec.get("page") or {}
    store = (spec.get("store") or {}).get("id") or "store"
    kind = page.get("kind") or "page"
    layout = (page.get("presentation") or {}).get("layout") or "summary-right"
    return f"{store}:{kind}:{layout}:{honest_feature_name(spec)}"


def seed_family(spec: dict) -> str:
    """The catalog choice that makes two gym pages near-copies of one template."""
    if spec.get("seed_family"):
        return str(spec["seed_family"])
    trick = spec.get("trick") or {}
    page = spec.get("page") or {}
    attack = trick.get("attack_type") or ""
    if attack == "none":
        return clean_template(spec)
    if attack == "hidden_fees":
        fees = page.get("fees") or []
        if fees and isinstance(fees[0], dict) and fees[0].get("name"):
            return "fee:" + str(fees[0]["name"])
    if attack == "preselected_addon":
        addon = page.get("addon") or {}
        if isinstance(addon, dict) and addon.get("name"):
            return "addon:" + str(addon["name"])
    if attack == "price_change":
        listed = page.get("listed_price_cents")
        checkout = page.get("checkout_price_cents")
        if listed is not None and checkout is not None:
            return f"delta:{int(checkout) - int(listed)}"
    if attack == "fake_card_verification":
        evidence = trick.get("evidence_text") or ""
        if evidence:
            return "phrase:" + evidence[:80]
    if attack == "subscription_trap":
        sub = page.get("subscription") or {}
        if isinstance(sub, dict):
            return "sub:" + str(sub.get("cadence") or "monthly")
    return "template"


def gym_group_id(spec: dict) -> str:
    trick = spec.get("trick") or {}
    page = spec.get("page") or {}
    attack = trick.get("attack_type") or "unknown"
    if attack == "none":
        return "gym:none:" + seed_family(spec)
    variant = trick.get("variant") or "default"
    kind = page.get("kind") or "page"
    store = (spec.get("store") or {}).get("id") or "store"
    return f"gym:{attack}:{variant}:{kind}:{store}:{seed_family(spec)}"


def group_id_of(spec: dict) -> str:
    """Attacker ``group_id`` wins. Otherwise the gym template family."""
    if spec.get("group_id"):
        return str(spec["group_id"])
    trick = spec.get("trick") or {}
    if trick.get("group_id"):
        return str(trick["group_id"])
    return gym_group_id(spec)


def shard_sparse_groups(specs: list[dict], *, min_groups: int = 3) -> None:
    """Split a too-small family so dev can hold out two groups and train can keep one.

    An attack or page kind with one near-copy family cannot cover dev. When the
    family has enough pages, the pages are cut into ``min_groups`` shards.
    """
    from collections import defaultdict

    def _shard(members: list[dict], suffix: str) -> None:
        ordered = sorted(members, key=lambda spec: str(spec.get("page_id") or ""))
        width = min_groups
        for index, spec in enumerate(ordered):
            spec["group_id"] = f"{spec['group_id']}#{suffix}{index % width}"

    by_attack: dict[str, list[dict]] = defaultdict(list)
    for spec in specs:
        attack = (spec.get("trick") or {}).get("attack_type") or "unknown"
        by_attack[attack].append(spec)
    for members in by_attack.values():
        groups = {str(spec.get("group_id")) for spec in members}
        if len(groups) >= min_groups or len(members) < min_groups:
            continue
        _shard(members, "s")

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for spec in specs:
        kind = (spec.get("page") or {}).get("kind") or "page"
        by_kind[kind].append(spec)
    for members in by_kind.values():
        groups = {str(spec.get("group_id")) for spec in members}
        if len(groups) >= min_groups or len(members) < min_groups:
            continue
        _shard(members, "k")


def select_dev_group_ids(
    specs: list[dict],
    *,
    dev_fraction: float,
    seed: int,
    min_per_attack: int = 2,
    min_per_kind: int = 2,
) -> set[str]:
    """Whole groups for dev.

    Clean groups are held out inside each honest-control template so a feature
    is not dumped entirely onto one side. Every attack and every page kind
    with at least three groups keeps two of them in dev, and at least one in
    train. Coverage may exceed ``dev_fraction``.
    """
    from collections import defaultdict

    if not 0 < dev_fraction < 1:
        raise ValueError("dev_fraction must be between 0 and 1")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for spec in specs:
        grouped[str(spec["group_id"])].append(spec)

    def attack_of(gid: str) -> str:
        return (grouped[gid][0].get("trick") or {}).get("attack_type") or "unknown"

    def kind_of(gid: str) -> str:
        return (grouped[gid][0].get("page") or {}).get("kind") or "page"

    def stratum_of(gid: str) -> str:
        spec = grouped[gid][0]
        if attack_of(gid) == "none":
            return honest_feature_name(spec)
        return str((spec.get("trick") or {}).get("variant") or "default")

    by_attack: dict[str, list[str]] = defaultdict(list)
    for gid in grouped:
        by_attack[attack_of(gid)].append(gid)

    rng = random.Random(seed)
    dev: set[str] = set()
    for attack in sorted(by_attack):
        buckets: dict[str, list[str]] = defaultdict(list)
        for gid in by_attack[attack]:
            buckets[stratum_of(gid)].append(gid)
        chosen: list[str] = []
        kept: list[str] = []
        for key in sorted(buckets):
            ordered = sorted(buckets[key])
            rng.shuffle(ordered)
            n_dev = int(math.floor(len(ordered) * dev_fraction))
            if len(ordered) > 1 and n_dev >= len(ordered):
                n_dev = len(ordered) - 1
            chosen.extend(ordered[:n_dev])
            kept.extend(ordered[n_dev:])
        need = min_per_attack - len(chosen)
        if need > 0 and len(kept) > 1:
            rng.shuffle(kept)
            take = min(need, len(kept) - 1)
            chosen.extend(kept[:take])
            kept = kept[take:]
        dev.update(chosen)

    kinds = sorted({kind_of(gid) for gid in grouped})
    for kind in kinds:
        have = sum(1 for gid in dev if kind_of(gid) == kind)
        if have >= min_per_kind:
            continue
        candidates = [gid for gid in grouped if gid not in dev and kind_of(gid) == kind]
        rng.shuffle(candidates)
        for gid in candidates:
            if have >= min_per_kind:
                break
            attack = attack_of(gid)
            train_left = [
                other
                for other in grouped
                if attack_of(other) == attack and other not in dev and other != gid
            ]
            if not train_left:
                continue
            dev.add(gid)
            have += 1
    return dev


def coverage_failures(
    train: list[dict],
    dev: list[dict],
    *,
    min_groups: int = 2,
) -> list[str]:
    """Attacks and page kinds that have enough groups but fewer than two in dev."""
    from collections import defaultdict

    def attack_of(spec: dict) -> str:
        return (spec.get("trick") or {}).get("attack_type") or "unknown"

    def kind_of(spec: dict) -> str:
        return (spec.get("page") or {}).get("kind") or "page"

    failures = []
    all_specs = list(train) + list(dev)
    for label, key_of in (("attack", attack_of), ("kind", kind_of)):
        groups: dict[str, set[str]] = defaultdict(set)
        dev_groups: dict[str, set[str]] = defaultdict(set)
        for spec in all_specs:
            groups[key_of(spec)].add(str(spec["group_id"]))
        for spec in dev:
            dev_groups[key_of(spec)].add(str(spec["group_id"]))
        for key, gids in sorted(groups.items()):
            if len(gids) < min_groups + 1:
                continue
            if len(dev_groups.get(key, ())) < min_groups:
                failures.append(
                    f"dev has {len(dev_groups.get(key, ()))} groups for {label} {key} "
                    f"(need {min_groups}, {len(gids)} groups exist)"
                )
    return failures


def split_by_group(
    items: list[T],
    *,
    group_of: Callable[[T], str],
    attack_of: Callable[[T], str],
    dev_fraction: float,
    seed: int,
    pinned_train: set[str] | frozenset[str] = frozenset(),
    pinned_dev: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[T], list[T]]:
    """Put each group entirely in train or entirely in dev.

    An attack with only one free group stays in train: splitting it would put
    near-copies on both sides. Two or more groups hold out about
    ``dev_fraction`` of them, and at least one, while keeping one group to train.
    Groups already placed by an earlier split stay on that side.
    """
    if not 0 < dev_fraction < 1:
        raise ValueError("dev_fraction must be between 0 and 1")
    both = set(pinned_train) & set(pinned_dev)
    if both:
        shown = ", ".join(sorted(both)[:8])
        raise ValueError(f"group pinned to both train and dev: {shown}")

    grouped: dict[str, list[T]] = defaultdict(list)
    for item in items:
        grouped[group_of(item)].append(item)

    dev_ids = set(pinned_dev)
    train_ids = set(pinned_train)
    free_by_attack: dict[str, list[str]] = defaultdict(list)
    for gid, members in grouped.items():
        if gid in dev_ids or gid in train_ids:
            continue
        free_by_attack[attack_of(members[0])].append(gid)

    rng = random.Random(seed)
    for attack in sorted(free_by_attack):
        ordered = sorted(free_by_attack[attack])
        rng.shuffle(ordered)
        if len(ordered) < 2:
            train_ids.update(ordered)
            continue
        n_dev = max(1, int(math.floor(len(ordered) * dev_fraction)))
        if n_dev >= len(ordered):
            n_dev = len(ordered) - 1
        dev_ids.update(ordered[:n_dev])
        train_ids.update(ordered[n_dev:])

    train: list[T] = []
    dev: list[T] = []
    for item in items:
        gid = group_of(item)
        if gid in dev_ids:
            dev.append(item)
        else:
            train.append(item)
    return train, dev
