.PHONY: test testset visa-demo

PY ?= python3

test:
	$(PY) -m pytest -q

testset:
	$(PY) -m gym.testset --check

visa-demo:
	$(PY) -m visa.demo
