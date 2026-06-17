image-base:
	podman build -f Dockerfile -t pyfilament/pyfilament:dev-latest .

image-ui:
	podman build -f ui/Dockerfile -t pyfilament/pyfilament-ui:dev-latest ui

image-website:
	podman build -f website/Dockerfile -t pyfilament/pyfilament-website:dev-latest website

install:
	uv sync --all-extras

upgrade:
	uv run alembic upgrade head

lint:
	uv run ruff check src/ --ignore F401,E402,E731,F841,F403,E712,E722,E711,F541

test:
	uv run pytest

test-coverage:
	uv run coverage run -m pytest

coverage-clean:
	rm -rf .coverage*

coverage-report:
	uv run coverage xml -o .coverage.xml && uv run coverage html -d .coverage_html && uv run diff-cover .coverage.xml --compare-branch=main --html-report .coverage_diff.html

coverage: coverage-clean test-coverage coverage-report
