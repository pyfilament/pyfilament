import asyncio

import anyio

from filament.filament import (
    generate_remote_task_run_results,
    get_logger,
    get_remote_task_run_results,
    task,
    wait_for_remote_task_run,
)


class CustomException(Exception):
    pass


@task(timeout=2.5, tries=2, delay=1.5, retry_exceptions=(CustomException, TimeoutError))
async def d(x):
    if x == 2:
        raise CustomException('Error in d')
    await asyncio.sleep(x)
    if x == 1:
        logger = get_logger()
        logger.info('hello from d')
        await f(x)
    # return await f.request(x)
    return await f(x)


@task
async def f(x):
    sync_result = sync(x, x)
    logger = get_logger()
    logger.info('hello from f, sync result: %s', sync_result)
    return x**2


@task(max_concurrent=1)
async def g():
    logger = get_logger()
    logger.info('hello from g')
    await asyncio.sleep(60)
    logger.info('hello from g, done')


@task
async def gen_root(remote=False):
    logger = get_logger()

    # test 1: aiter
    generator = gen()
    # generator = gen.request(propagate=False)
    i_s = []
    async for i in generator:
        logger.info('hello from gen_root, i: %s', i)
        i_s.append(i)
    assert i_s == list(range(10))

    # test 2: call
    generator = gen()
    # generator = gen.request(propagate=False)
    j = await generator
    logger.info('hello from gen_root, return result: %s', j)
    assert j == 9


@task
async def gen_root_listen():
    logger = get_logger()
    remote_task = gen.request(propagate=False)
    # remote_task = gen.request(propagate=False, start_immediately=True)

    async def _start_gen(remote_task):
        async for i in remote_task:
            logger.info('hello from gen_root, i: %s', i)

    async def _listen_for_task(remote_task):
        async for i in generate_remote_task_run_results(remote_task.uuid, propagate=False):
            logger.info('hello from gen_root listening, i: %s', i)

    async with anyio.create_task_group() as tg:
        tg.start_soon(_start_gen, remote_task)
        tg.start_soon(_listen_for_task, remote_task)

    logger.info('gen_root waiting for gen to finish')
    await wait_for_remote_task_run(remote_task.uuid)
    logger.info('gen_root finished waiting for gen')

    logger.info('gen_root getting final result')
    final_result = await get_remote_task_run_results(remote_task.uuid)
    logger.info('gen_root final result: %s', final_result)


@task
async def gen():
    for i in range(10):
        # if i == 5:
        #     raise CustomException('Error in gen')
        await asyncio.sleep(0.2)
        yield i


@task(rate_limit=1)
async def h():
    return


@task
def sync(a, b):
    logger = get_logger()
    logger.info('hello from sync')
    return a + b


"""
four tasks:
1. succeeds after 1 second, calls child tasks, first success, second cached (1s), run counts = 1, 1, 0
2. fails immediately, delays for 1.5 seconds, fails again (1.5s), run count = 2
3. times out after 2.5 seconds (would've ran for 3), delays for 1.5 seconds, then times out again after 2.5 seconds (total 6.5s), run count = 2
4. canceled after 1.5 seconds. cancel monitor after an integer number of seconds, will cancel the task group (total 1.5-2.5s), run count = 1
"""


@task
async def root():
    print('Starting root task')
    tasks = [d(i + 1, start_immediately=True) for i in range(4)]
    await anyio.sleep(1.5)
    print('Cancelling last task')
    await tasks[-1].cancel()
    print('Waiting for tasks to finish')
    results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f'Results: {results}')
    # return results
