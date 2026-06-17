[![pypi package version](https://img.shields.io/pypi/v/pyfilament)](https://pypi.org/project/pyfilament/) [![python version](https://img.shields.io/pypi/pyversions/pyfilament)](https://pypi.org/project/pyfilament/) [![pytest](https://github.com/pyfilament/pyfilament/actions/workflows/pytest.yml/badge.svg)](https://github.com/pyfilament/pyfilament/actions/workflows/pytest.yml) [![codecov](https://codecov.io/github/pyfilament/pyfilament/graph/badge.svg?token=DIUIQG3YMW)](https://codecov.io/github/pyfilament/pyfilament) [![discord](https://img.shields.io/discord/1516547508837285958?logo=discord)](https://discord.gg/RgyZceR53B)

# pyfilament

lightweight task framework

Features
* timeouts / retries / caching
* token-bucket and concurrency limits
* subtasks, queues, and distributed workers
* task cancellation and graceful worker shutdown
* state timeline tracking, logging, args inspection

# Getting Started

```
uv add pyfilament
uv run - << 'EOF'
from filament import task
from asyncio import run

@task
async def foo():
    return 'bar'

run(foo())
EOF
```
