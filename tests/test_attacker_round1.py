"""Round-1 attacker specs stay off the frozen test set, including short lines."""

from attacker.check_near_duplicates import find_hits, load_corpus, main, prose_strings


def _hits(text: str) -> list[str]:
    phrases, slices = _hits.corpus
    return find_hits({"blurb": text}, phrases, slices)


_hits.corpus = load_corpus()


def test_short_test_lines_hit_and_ordinary_copy_does_not():
    assert _hits("No thanks")
    assert _hits("No thanks. I love chaos!")
    assert _hits("Total")
    assert _hits("bank password")
    assert _hits("Arrives in 2 business days from a U.S. warehouse.")
    assert _hits("checkbox")
    assert _hits("A fair fee for the price of shipping.") == []


def test_known_variant_token_is_not_copy():
    spec = {
        "trick": {"variant": "checkbox", "attack_type": "preselected_addon"},
        "page": {"title": "A fair linen sack"},
    }
    assert prose_strings(spec) == [("page.title", "A fair linen sack")]
    assert find_hits(spec, *_hits.corpus) == []


def test_round1_batch_is_clear_of_the_test_set():
    assert main() == 0
