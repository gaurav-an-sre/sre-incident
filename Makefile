PYTHON := .venv/bin/python

.PHONY: up shop deploy rollback test lint

up:
	$(PYTHON) -m uvicorn checkout_svc.main:app --host 0.0.0.0 --port 8000

shop:
	$(PYTHON) -m tools.shopper

deploy:
	$(PYTHON) -m tools.deploy promo

rollback:
	$(PYTHON) -m tools.deploy rollback

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy checkout_svc tools
