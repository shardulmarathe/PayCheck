"""Clean pages must show the same widgets trick pages show, at a similar rate."""

from collections import Counter

from gym.catalog import seed_for_round
from gym.render import render_html, structural_features
from gym.testset import frozen_specs
from gym.train import training_specs

FEATURES = ("checkbox", "popup", "fee", "strike")
EXTRA = ("radio",)
MIN_RELATIVE = 0.25


def _groups(specs: list[dict]) -> tuple[list[dict], list[dict]]:
    clean = [spec for spec in specs if spec["trick"]["attack_type"] == "none"]
    trick = [spec for spec in specs if spec["trick"]["attack_type"] != "none"]
    return clean, trick


def _hits(specs: list[dict]) -> Counter:
    hits: Counter = Counter()
    for spec in specs:
        found = structural_features(render_html(spec))
        for name, present in found.items():
            if present:
                hits[name] += 1
        if any(found[name] for name in FEATURES):
            hits["any"] += 1
    return hits


def _table(sets: dict[str, list[dict]]) -> str:
    lines = [
        f"{'set':<8} {'feature':<10} {'clean':>12} {'trick':>12} {'relative':>10}",
    ]
    for name, specs in sets.items():
        clean, trick = _groups(specs)
        clean_hits = _hits(clean)
        trick_hits = _hits(trick)
        for feature in (*FEATURES, *EXTRA, "any"):
            if feature == "any":
                left = f"{clean_hits['any']}/{len(clean)}"
                right = ""
                relative = ""
            else:
                left = f"{clean_hits[feature]}/{len(clean)}"
                right = f"{trick_hits[feature]}/{len(trick)}"
                if trick_hits[feature] == 0:
                    relative = "n/a"
                else:
                    relative = f"{(clean_hits[feature] / len(clean)) / (trick_hits[feature] / len(trick)):.2f}"
            lines.append(f"{name:<8} {feature:<10} {left:>12} {right:>12} {relative:>10}")
    return "\n".join(lines)


def test_clean_pages_match_trick_structure_at_least_a_quarter_of_the_rate(capsys):
    sets = {
        "test": frozen_specs(),
        "train": training_specs(100, seed_for_round(1), round_n=1),
    }
    table = _table(sets)
    print(table)
    failures = []
    for name, specs in sets.items():
        clean, trick = _groups(specs)
        clean_hits = _hits(clean)
        trick_hits = _hits(trick)
        for feature in (*FEATURES, *EXTRA):
            if trick_hits[feature] == 0:
                continue
            clean_rate = clean_hits[feature] / len(clean)
            trick_rate = trick_hits[feature] / len(trick)
            if clean_rate < MIN_RELATIVE * trick_rate:
                failures.append(
                    f"{name} {feature}: clean {clean_rate:.3f} is under "
                    f"{MIN_RELATIVE:.0%} of trick {trick_rate:.3f}"
                )
        if name == "test" and clean_hits["any"] / len(clean) < 0.45:
            failures.append(
                f"test clean pages with a structural feature: "
                f"{clean_hits['any']}/{len(clean)}"
            )
    assert not failures, table + "\n" + "\n".join(failures)
    captured = capsys.readouterr()
    assert "checkbox" in captured.out


def test_honest_controls_keep_the_clean_label():
    for spec in frozen_specs():
        if spec["trick"]["attack_type"] != "none":
            continue
        trick = spec["trick"]
        assert trick["verdict"] == "pass"
        assert trick["selector"] == ""
        assert trick["evidence_text"] == ""
        assert trick["instruction"] == ""
        assert spec["page"]["listed_price_cents"] == spec["page"]["checkout_price_cents"]
        html = render_html(spec)
        assert 'id="trick"' not in html
        offers = spec["page"].get("offers") or {}
        checkbox = offers.get("checkbox")
        if checkbox:
            assert checkbox["checked"] is False
            assert 'id="opt-in" name="opt_in" value="1"' in html
            assert "checked" not in html.split('id="opt-in"', 1)[1][:40]
        modal = offers.get("modal")
        if modal:
            assert modal["decline"] == "No thanks"
            assert html.index(">No thanks<") < html.index(f">{modal['accept']}<")
            assert all(not item.get("trick_item") for item in spec["page"]["cart"])
            assert modal["name"] not in [item["name"] for item in spec["page"]["cart"]]
        if spec["page"]["fees"]:
            assert "data-fee=" in html
        was = offers.get("was_cents")
        if was:
            assert was > spec["page"]["checkout_price_cents"]
            assert 'class="was"' in html
        radios = offers.get("radios")
        if radios:
            selected = [option for option in radios["options"] if option["checked"]]
            assert len(selected) == 1
