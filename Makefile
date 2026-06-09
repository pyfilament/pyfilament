image-base:
	podman build -f Dockerfile -t pyfilament/filament-base:dev-latest .

image-ui:
	podman build -f ui/Dockerfile -t pyfilament/ui:dev-latest ui

install:
	poetry install

upgrade:
	poetry run alembic upgrade head

lint:
	poetry run ruff check src/ --ignore F401,E402,E731,F841,F403,E712,E722,E711,F541

test:
	poetry run pytest
