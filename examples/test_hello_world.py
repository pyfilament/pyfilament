import asyncio
import logging

from filament import get_logger, task

logging.getLogger().setLevel(logging.DEBUG)


@task
async def make_greeting():
    logger = get_logger()
    logger.info('Building greeting')
    await asyncio.sleep(0.1)
    return 'world'


@task
async def say_hello():
    logger = get_logger()
    logger.info('Saying hello')
    await asyncio.sleep(0.1)
    greeting = await make_greeting()
    await asyncio.sleep(0.1)
    return f'Hello, {greeting}!'


async def test_hello_world() -> None:
    assert await say_hello() == 'Hello, world!'
