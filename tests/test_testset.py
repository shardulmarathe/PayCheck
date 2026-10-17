import json
from collections import Counter

from gym.paths import manifest_path, slice_path
from gym.paths import testset_dir as frozen_pages
from gym.taxonomy import HELD_OUT, SLICE_COUNTS
from gym.testset import check_testset, composition
from gym.validate import guard_from_label, validate_guard_output, validate_label


def _labels():
    rows = []
    for line in (frozen_pages() / "labels.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_committed_testset_composition_and_guard_contract():
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    labels = _labels()
    assert len(labels) == 300
    assert manifest["page_count"] == 300
    assert manifest["viewport"] == [1280, 800]
    counts = composition(labels)
    assert counts == manifest["composition"]
    assert counts["none"] == 150
    assert sum(count for attack, count in counts.items() if attack != "none") == 150
    assert HELD_OUT <= set(counts)
    families = Counter(row["family"] for row in labels)
    assert families["clean"] == 150
    for row in labels:
        validate_label(row)
        guard = guard_from_label(row)
        validate_guard_output(guard)
        html = (frozen_pages() / "html" / f"{row['page_id']}.html").read_text(encoding="utf-8")
        text = (frozen_pages() / "text" / f"{row['page_id']}.txt").read_text(encoding="utf-8")
        if row["verdict"] == "block":
            assert row["evidence_text"] in html or row["evidence_text"] in text
            assert row["evidence_text"] in text
            assert row["bbox"][2] > 0 and row["bbox"][3] > 0
        else:
            assert row["bbox"] is None
            assert 'id="trick"' not in html
    slice_ids = [
        line.strip()
        for line in slice_path().read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(slice_ids) == 100
    by_id = {row["page_id"]: row for row in labels}
    slice_counts = Counter(by_id[page_id]["attack_type"] for page_id in slice_ids)
    assert dict(slice_counts) == SLICE_COUNTS
    assert len(manifest["content_hash"]) == 64


def test_make_testset_reproduces_the_hash():
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    digest = check_testset()
    assert digest == manifest["content_hash"]
