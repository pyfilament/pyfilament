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

# Optional Dependencies

pyfilament makes use of redis for task queueing, and a SQL database for state tracking. Both of these dependencies are optional, but will enable user-facing features.

## Redis (queueing)

Enables distributed workloads using queues and workers (`my_task.request()` and `my_task.serve()`). Redis is also required for caching. By default, pyfilament will attempt to connect to `localhost:6379`. You can override it with

```
export FILAMENT_REDIS_HOST=new_redis_host
export FILAMENT_REDIS_PORT=6379
```

## State tracking

Enables frontend ui dashboard, API-triggered task cancellations, and STONITH. By default, pyfilament will use a local sqlite database. You can override it with:

```
export FILAMENT_DB_URI=postgresql+asyncpg://username:password@hostname:5432/dbname
```

## Disabling optional dependencies

The default `@task` decorator (`from filament import task`) assumes that both are enabled. There's plans to make disabling optional dependencies easier in a future release, but for now look in these tests for examples of how run without optional dependencies:

|test name|queueing|state tracking|
|---|---|---|
|[tests/test_task.py](tests/test_task.py)|disabled|disabled|
|[tests/test_queue.py](tests/test_queue.py)|enabled|disabled|
|[tests/test_cancel_state.py](tests/test_cancel_state.py)|disabled|enabled|
|default `@task`|enabled|enabled|
