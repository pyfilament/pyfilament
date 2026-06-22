"""A minimal pyfilament example: a streaming weather agent powered by the Anthropic API.

Run it from the repo root (requires: `anthropic`):

    uv sync --group examples
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run pytest examples/test_get_weather.py -s
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic

from filament import get_logger, task

MODEL = 'claude-sonnet-4-6'
MAX_TURNS = 10
logging.getLogger().setLevel(logging.DEBUG)

client = AsyncAnthropic()

WEATHER_TOOL = {
    'name': 'get_weather',
    'description': 'Get the current weather for a city.',
    'input_schema': {
        'type': 'object',
        'properties': {'city': {'type': 'string', 'description': 'City name, e.g. "Paris"'}},
        'required': ['city'],
    },
}

FAKE_WEATHER = {
    'paris': '18°C, light rain',
    'tokyo': '24°C, clear',
    'new york': '21°C, partly cloudy',
    'cairo': '33°C, sunny',
}


### TOOLS


@task
async def get_weather(city: str) -> str:
    get_logger().info('Looking up weather for %s', city)
    return FAKE_WEATHER.get(city.lower(), f'No data for {city}; assume 20°C and mild.')


### AGENT


# An async-generator @task: yielded values stream to the caller via `async for`.
# Yields answer tokens (str), then the final message (dict) for the tool loop.
@task
async def generate_response(messages: list[dict]) -> AsyncGenerator[str | dict, None]:
    async with client.messages.stream(model=MODEL, max_tokens=1024, tools=[WEATHER_TOOL], messages=messages) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
        get_logger().info('LLM call: stop=%s', final.stop_reason)
        yield {'stop_reason': final.stop_reason, 'content': [b.model_dump(exclude_none=True) for b in final.content]}


# Consumes the generate_response stream with `async for` and re-yields tokens, so it's
# itself a streaming @task. Each get_weather and generate_response call is its own run.
@task
async def answer_weather_question(question: str) -> AsyncGenerator[str, None]:
    get_logger().info('Question: %s', question)
    messages: list[dict] = [{'role': 'user', 'content': question}]
    for _ in range(MAX_TURNS):
        reply = None
        async for event in generate_response(messages):
            if isinstance(event, str):
                yield event
            else:
                reply = event
        messages.append({'role': 'assistant', 'content': reply['content']})
        if reply['stop_reason'] != 'tool_use':
            return
        tool_results = []
        for block in reply['content']:
            if block['type'] != 'tool_use':
                continue
            assert block['name'] == 'get_weather', f'Unexpected tool: {block["name"]}'
            weather = await get_weather(block['input']['city'])
            tool_results.append({'type': 'tool_result', 'tool_use_id': block['id'], 'content': weather})
        messages.append({'role': 'user', 'content': tool_results})
    raise RuntimeError(f'No final answer after {MAX_TURNS} turns')


### RUN


@task
async def print_weather_answers() -> None:
    questions = [
        'What is the weather in Paris?',
        'Should I bring sunglasses in Cairo or Tokyo right now?',
    ]
    for question in questions:
        print(f'Q: {question}\nA: ', end='', flush=True)
        async for chunk in answer_weather_question(question):
            print(chunk, end='', flush=True)
        print('\n')


async def test_get_weather():
    await print_weather_answers()
