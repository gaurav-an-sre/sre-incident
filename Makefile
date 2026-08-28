PYTHON := .venv/bin/python

.PHONY: up shop deploy rollback test lint demo-dry verify verify-wrong-fix verify-correct-fix

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
	$(PYTHON) -m mypy checkout_svc tools payments incident_agents verify

demo-dry:
	$(PYTHON) -m incident_agents investigate --incident inc-20260828T054250Z-696028f6 --dry-run --fresh
	$(PYTHON) -m incident_agents remediate --incident inc-20260828T054250Z-696028f6 --dry-run --fresh
	$(PYTHON) -m incident_agents publish --incident inc-20260828T054250Z-696028f6 --dry-run

verify:
	$(PYTHON) -m verify --candidate HEAD --json out/verification.json

verify-wrong-fix:
	$(PYTHON) -m verify.wrong_fix

verify-correct-fix:
	$(PYTHON) -m verify.correct_fix
