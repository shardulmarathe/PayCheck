.PHONY: test testset

PY ?= python3

test:
	$(PY) -m pytest -q

testset:
	$(PY) -m gym.testset --check
