import asyncio
import logging

from .app import analyze_page, register_task_types

logging.getLogger().setLevel(logging.DEBUG)


async def main() -> None:
    # Register every task type up front (serially, under a lock) so concurrent runs
    # never race to insert the same row, then serve analyze_page off the queue. Run
    # this in as many terminals as you like — workers share the queue and the global
    # max_concurrent cap. Run from the repo root: python -m examples.web_analyst.worker
    await register_task_types()
    print('worker ready — serving analyze_page (submit jobs in another terminal)')
    await analyze_page.serve()


if __name__ == '__main__':
    asyncio.run(main())
