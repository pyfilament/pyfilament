"""Command-line entrypoint for the web analyst: analyze URLs from the command line.

Reuses the pipeline defined in test_web_analyst.py. Run from the repo root:

    uv run python -m examples.web_analyst.cli [urls...]
"""

import asyncio
import sys

from .test_web_analyst import DEFAULT_URLS, run_web_analyst_pipeline

asyncio.run(run_web_analyst_pipeline(sys.argv[1:] or DEFAULT_URLS))
