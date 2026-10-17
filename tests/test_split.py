from gym.dataset import compute_split, load_rows, load_split, rows_for_ids
from gym.taxonomy import SPLIT_SEED, TEST_FRACTION


def test_committed_split_matches_the_seed_algorithm():
    assert (SPLIT_SEED, TEST_FRACTION) == (20261017, 0.25)
    train, test = load_split()
    expected_train, expected_test = compute_split()
    assert train == expected_train
    assert test == expected_test
    assert set(train).isdisjoint(test)
    rows = load_rows()
    assert set(train) | set(test) == {row["page_id"] for row in rows}
    assert rows_for_ids(rows, test)
    assert rows_for_ids(rows, train)


def test_every_string_from_a_page_stays_in_one_pile():
    rows = load_rows()
    train, test = load_split()
    train_set, test_set = set(train), set(test)
    for row in rows:
        assert (row["page_id"] in train_set) ^ (row["page_id"] in test_set)
