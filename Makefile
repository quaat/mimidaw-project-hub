.PHONY: test check run init up down logs smoke
init:
	./scripts/init-env.sh
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f hub
run:
	uvicorn hub.app:app --host 127.0.0.1 --port 8090 --reload
test:
	python -m pytest -q
check:
	python -m compileall -q hub tests scripts
	python -m pytest -q
smoke:
	python scripts/smoke.py
