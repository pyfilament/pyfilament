import asyncio
import sys

from .app import DEFAULT_URLS, run_web_analyst_pipeline

# Client entrypoint — submit jobs to the queue. Run from the repo root:
#   python -m examples.web_analyst [urls...]
asyncio.run(run_web_analyst_pipeline(sys.argv[1:] or DEFAULT_URLS))
