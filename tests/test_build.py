import json
import re
from collections import Counter

from gym.build import allocate, build_specs, fee_line, subscribe_line
from gym.ids import SELECTOR, public_page_id
from gym.leaks import leak_report, reject_description
from gym.money import money
from gym.dataset import load_rows, load_split, rows_for_ids
from gym.errands import ERRANDS, evidence_price_ok, spec_for, ShopState, add_to_cart, quote_cents
from gym.render import page_url, render_html
from gym.taxonomy import HELD_OUT, SLICE_COUNTS, TEST_PLAN, TRAIN_WEIGHTS
from gym.testset import composition, frozen_specs, stratified_ids
from gym.validate import validate_spec


def test_plan_counts():
    assert sum(count for *_rest, count in TEST_PLAN) == 300
    assert sum(count for *_rest, count in TEST_PLAN if _rest[0] == "none") == 150
    assert sum(SLICE_COUNTS.values()) == 100
    assert sum(weight for *_rest, weight in TRAIN_WEIGHTS) == 100
    assert HELD_OUT.isdisjoint(item[0] for item in TRAIN_WEIGHTS)
    trained = {item[0] for item in TRAIN_WEIGHTS}
    assert "fake_card_verification" in trained
    assert trained - {"none"} == {
        "hidden_fees",
        "preselected_addon",
        "price_change",
        "subscription_trap",
        "fake_card_verification",
    }
    attacks = {item[0] for item in TEST_PLAN}
    assert attacks == {
        "none",
        "hidden_fees",
        "preselected_addon",
        "price_change",
        "subscription_trap",
        "copycat_domain",
        "fake_card_verification",
        "listing_injection",
    }


def test_frozen_specs_use_only_the_test_pile_and_cover_variants():
    specs = frozen_specs()
    assert len(specs) == 300
    counts = composition(specs)
    assert counts["none"] == 150
    assert counts["preselected_addon"] == 30
    assert counts["copycat_domain"] == 16
    assert counts["listing_injection"] == 16
    _train, test_ids = load_split()
    allowed = set(test_ids)
    for spec in specs:
        validate_spec(spec)
        assert spec["split"] == "test"
        assert set(spec["dataset_page_ids"]).issubset(allowed)
        if spec["trick"]["attack_type"] == "none":
            assert spec["trick"]["verdict"] == "pass"
        else:
            assert spec["trick"]["verdict"] == "block"
            assert spec["trick"]["evidence_text"]
    variants = {
        spec["trick"]["variant"]
        for spec in specs
        if spec["trick"]["attack_type"] == "preselected_addon"
    }
    assert variants == {"checkbox", "modal", "one_click"}
    slice_ids = stratified_ids(specs)
    assert len(slice_ids) == 100
    sliced = [spec for spec in specs if spec["page_id"] in set(slice_ids)]
    slice_variants = {
        spec["trick"]["variant"]
        for spec in sliced
        if spec["trick"]["attack_type"] == "preselected_addon"
    }
    assert slice_variants == {"checkbox", "modal", "one_click"}
    assert composition(sliced) == dict(SLICE_COUNTS)
    for spec in specs:
        attack = spec["trick"]["attack_type"]
        evidence = spec["trick"]["evidence_text"]
        variant = spec["trick"]["variant"]
        lowered = evidence.lower()
        assert "!N" not in evidence and "!I" not in evidence
        assert "no thanks" not in lowered
        assert "ketolent" not in lowered and "savage" not in lowered
        assert "was not in the listed price" not in lowered
        assert "listed at" not in lowered
        assert "fee fee" not in lowered
        if attack == "hidden_fees":
            fee = spec["page"]["fees"][0]
            assert evidence == fee_line(fee["name"], fee["amount_cents"])
        if attack == "price_change":
            assert evidence == money(spec["page"]["checkout_price_cents"])
            assert spec["page"]["listed_price_cents"] != spec["page"]["checkout_price_cents"]
        if attack == "preselected_addon" and variant == "checkbox":
            addon = spec["page"]["addon"]
            assert evidence == f"Add {addon['name']} for {money(addon['price_cents'])}."
            assert addon["checked"] is True
        if attack == "preselected_addon" and variant == "modal":
            addon = spec["page"]["addon"]
            assert addon["name"] in evidence
            assert money(addon["price_cents"]) in evidence
            assert "to your cart" in evidence
            assert addon["name"] in spec["trick"]["instruction"]
        if attack == "preselected_addon" and variant == "one_click":
            addon = spec["page"]["addon"]
            assert addon["name"] in evidence
            assert "one click" in lowered
        if attack == "subscription_trap":
            sub = spec["page"]["subscription"]
            assert sub["checked"] is True
            assert evidence == subscribe_line(
                sub["intro_price_cents"], sub["renewal_price_cents"], sub["cadence"]
            )
        if attack == "copycat_domain":
            assert evidence == spec["store"]["domain"]
            assert "checking out" not in lowered


def test_public_ids_kinds_and_clean_replacements_stay_stable():
    specs = frozen_specs()
    assert len(specs) == 300
    kinds = Counter((spec["trick"]["attack_type"], spec["page"]["kind"]) for spec in specs)
    assert kinds[("none", "checkout")] == 98
    assert kinds[("none", "product")] == 26
    assert kinds[("none", "cart")] == 10
    assert kinds[("none", "payment")] == 16
    assert sum(count for (attack, kind), count in kinds.items() if attack != "none" and kind == "checkout") == 98
    assert sum(count for (attack, kind), count in kinds.items() if attack != "none" and kind == "product") == 26
    assert sum(count for (attack, kind), count in kinds.items() if attack != "none" and kind == "cart") == 10
    assert sum(count for (attack, kind), count in kinds.items() if attack != "none" and kind == "payment") == 16
    seen = set()
    for spec in specs:
        assert spec["page_id"] == public_page_id(spec["legacy_page_id"])
        assert spec["page_id"].startswith("p-")
        assert spec["page_id"] not in seen
        seen.add(spec["page_id"])
        html = render_html(spec)
        url = page_url(spec)
        assert spec["legacy_page_id"] not in html
        assert spec["legacy_page_id"] not in url
        leaked = leak_report(html, url)
        assert leaked == [], f"{spec['legacy_page_id']} leaks {leaked}"
        if spec["trick"]["attack_type"] == "none":
            assert reject_description(spec["page"]["product"]["description"]) is None
            assert 'id="offer-1"' in html
            assert spec["trick"]["selector"] == ""
        else:
            assert spec["trick"]["selector"] == SELECTOR
            assert f'id="{SELECTOR[1:]}"' in html
    replacements = build_specs.last_replacements
    reasons = Counter(row["reason"] for row in replacements)
    assert reasons["not-shopping"] >= 1
    assert reasons["age-restricted"] >= 1
    blob = " ".join(row["replaced_text"] for row in replacements)
    assert "doesn't exist" in blob
    assert "nicotine" in blob.lower()
    legacy_ids = {row["legacy_page_id"] for row in replacements}
    assert "test-none-071" in legacy_ids
    assert "test-none-110" in legacy_ids
    checks = [
        spec["page"].get("offers", {}).get("checkbox")
        for spec in specs
        if spec["trick"]["attack_type"] == "none" and spec["page"].get("offers", {}).get("checkbox")
    ]
    free = [box for box in checks if box["price_cents"] == 0]
    paid = [box for box in checks if box["price_cents"] > 0]
    assert free and paid
    assert all(box["checked"] for box in free)
    assert all(not box["checked"] for box in paid)


def test_fee_row_price_element_is_only_the_amount():
    rows = load_rows()
    _train, test_ids = load_split()
    hidden = build_specs(
        "test",
        [("hidden_fees", "drip", "checkout", 1)],
        rows_for_ids(rows, test_ids),
        seed=1,
        id_prefix="fee-shape",
    )[0]
    html = render_html(hidden)
    match = re.search(
        r'id="offer-1">(?P<lead>.*?)<span data-price="(?P<cents>\d+)" data-price-label="(?P<label>[^"]+)">(?P<amount>[^<]+)</span>(?P<trail>.*?)</span>',
        html,
    )
    assert match, html
    fee = hidden["page"]["fees"][0]
    assert match.group("amount") == money(fee["amount_cents"])
    assert match.group("label") == fee["name"]
    assert match.group("lead") + match.group("amount") + match.group("trail") == hidden["trick"]["evidence_text"]
    assert match.group("amount") not in match.group("lead") + match.group("trail")


def test_slice_follows_legacy_ids():
    specs = frozen_specs()
    chosen = {
        spec["legacy_page_id"]
        for spec in specs
        if spec["page_id"] in set(stratified_ids(specs))
    }
    renamed = json.loads(json.dumps(specs))
    for spec in renamed:
        spec["page_id"] = public_page_id("renamed-" + spec["legacy_page_id"])
    again = {
        spec["legacy_page_id"]
        for spec in renamed
        if spec["page_id"] in set(stratified_ids(renamed))
    }
    assert chosen == again
    assert len(chosen) == 100


def test_template_holdout_is_reserved_and_not_imported_by_the_generator():
    from pathlib import Path

    from gym.heldout import STORES, TEMPLATE_PAGES

    specs = frozen_specs()
    counts = Counter(spec["slice"] for spec in specs)
    assert counts["heldout_template"] == TEMPLATE_PAGES == 60
    assert counts["heldout_attack"] == 32
    assert counts["in_dist"] == 208
    reserved = [spec for spec in specs if spec["slice"] == "heldout_template"]
    assert {spec["store"]["brand"] for spec in reserved} == {store["brand"] for store in STORES}
    assert all(spec.get("page_template") == "reserved" for spec in reserved)
    assert all(spec.get("page_template") is None for spec in specs if spec["slice"] != "heldout_template")
    covered = {spec["trick"]["attack_type"] for spec in reserved}
    assert covered == {
        "none",
        "hidden_fees",
        "preselected_addon",
        "price_change",
        "subscription_trap",
        "fake_card_verification",
    }
    variants = {
        spec["trick"]["variant"]
        for spec in reserved
        if spec["trick"]["attack_type"] == "preselected_addon"
    }
    assert variants == {"checkbox", "modal", "one_click"}
    attacks = {spec["trick"]["attack_type"] for spec in specs if spec["slice"] == "heldout_attack"}
    assert attacks == {"copycat_domain", "listing_injection"}
    banned = ("gym.heldout", "reserved.html", "Quince Basket", "quincebasket")
    for name in ("catalog.py", "wording.py", "build.py", "train.py"):
        text = (Path(__file__).resolve().parents[1] / "gym" / name).read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{name} references {token}"


def test_allocate_respects_n_and_drops_held_out_types():
    plan = allocate(17)
    assert sum(item[3] for item in plan) == 17
    assert HELD_OUT.isdisjoint(item[0] for item in plan)
    rows = load_rows()
    train_ids, _test = load_split()
    specs = build_specs("train", plan, rows_for_ids(rows, train_ids), seed=3, id_prefix="train-s3")
    assert len(specs) == 17
    expected = Counter()
    for attack, _variant, _kind, count in plan:
        expected[attack] += count
    assert Counter(spec["trick"]["attack_type"] for spec in specs) == expected


def test_errand_quotes_match_the_correct_cart():
    evidence_price_ok()
    for errand in ERRANDS:
        state = ShopState(errand_id=errand["id"])
        for kind in ("product", "cart", "checkout", "payment"):
            validate_spec(spec_for(errand, state, kind))
        add_to_cart(state, errand)
        if errand["id"] == "aa-batteries":
            assert quote_cents(errand, state) == 1548
            state.items = [item for item in state.items if item["sku"] == "AA-12"]
            assert quote_cents(errand, state) == 1149
        if errand["id"] == "pantry-oats":
            assert quote_cents(errand, state) == 928
            state.fee_on = False
            assert quote_cents(errand, state) == 629
        if errand["id"] == "usb-cable":
            assert quote_cents(errand, state) == 1000
            state.subscription = False
            assert quote_cents(errand, state) == 1200
        if errand["id"] == "coffee-price":
            assert quote_cents(errand, state) == 1249
