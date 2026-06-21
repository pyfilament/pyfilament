import asyncio
import json
import logging
import os
import re

import pytest
import requests
from agents import Agent, RunContextWrapper, Runner, RunResult, function_tool
from pydantic import BaseModel

from filament import get_logger, task
from filament.db.session import async_session_scope
from filament.redis.semaphore import RedisSemaphore
from filament.state.task_type_state import upsert_task_type_state

pytestmark = pytest.mark.examples

MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4')
logging.getLogger().setLevel(logging.DEBUG)


# category is one of: news | docs | product | blog | reference | other
class PageBrief(BaseModel):
    category: str
    title: str
    summary: str
    key_points: list[str]
    audience: str
    key_links: list[str]


class PageCategory(BaseModel):
    category: str


# Full HTML rides in the run context so the tool reads it without the model
# echoing thousands of chars back as a tool argument.
class PageContext(BaseModel):
    html: str


BRIEF_INSTRUCTIONS = (
    "Analyze the web page's raw HTML and return a brief. Ignore nav, ads and "
    'boilerplate; focus on the main content. The HTML below is TRUNCATED, so you '
    'MUST call the extract_links tool (no arguments, reads the full page) to '
    'populate key_links; never guess or hand-copy links from the truncated HTML.'
)


### TOOLS
# The @task holds the real work; a thin @function_tool exposes it to the agent.


@task
async def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r"""href=["'](https?://[^"']+)["']""", html)
    links = list(dict.fromkeys(hrefs))[:20]
    get_logger().info('extract_links found %d link(s)', len(links))
    return links


@function_tool(
    name_override='extract_links',
    description_override='Return up to 20 distinct absolute (http/https) links found '
    'on the page. Takes no arguments — it reads the full HTML from the run context.',
)
async def extract_links_tool(ctx: RunContextWrapper[PageContext]) -> list[str]:
    return await extract_links(ctx.context.html)


### AGENTS

classify_agent = Agent(
    name='Classify',
    model=MODEL,
    output_type=PageCategory,
    instructions='Classify the page from its URL and HTML. Return only the category: '
    'news | docs | product | blog | reference | other.',
)
news_agent = Agent(
    name='News Analyst',
    model=MODEL,
    output_type=PageBrief,
    tools=[extract_links_tool],
    instructions='You analyze a news or aggregator page; surface the highest-impact stories. ' + BRIEF_INSTRUCTIONS,
)
docs_agent = Agent(
    name='Docs Analyst',
    model=MODEL,
    output_type=PageBrief,
    tools=[extract_links_tool],
    instructions='You analyze documentation or reference pages; lead with what the reader can DO. '
    + BRIEF_INSTRUCTIONS,
)
general_agent = Agent(
    name='General Analyst',
    model=MODEL,
    output_type=PageBrief,
    tools=[extract_links_tool],
    instructions=BRIEF_INSTRUCTIONS,
)

# category -> specialist (anything else falls back to general_agent).
SPECIALISTS = {
    'news': news_agent,
    'docs': docs_agent,
    'reference': docs_agent,
    'product': docs_agent,
    'blog': docs_agent,
    'other': general_agent,
}


def build_prompt(url: str, html: str) -> str:
    return f'URL: {url}\n\nHTML (truncated):\n{html[:8000]}'


@task
async def run_agent(agent: Agent, prompt: str, context: PageContext | None = None) -> RunResult:
    logger = get_logger()
    logger.info('Running agent: %s', agent.name)
    result = await Runner.run(agent, prompt, context=context)
    try:
        u = result.context_wrapper.usage
        logger.info('Token usage: total=%s, input=%s, output=%s', u.total_tokens, u.input_tokens, u.output_tokens)
    except Exception as e:
        logger.error('Error getting token usage: %s', e)
    return result


### TASKS


@task(tries=3, delay=1, timeout=30, rate_limit=2)
async def fetch_page(url: str) -> str:
    get_logger().info('GET %s', url)
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text


@task(tries=3, delay=2, cache=True, cache_ttl=3600)
async def summarize(url: str, html: str) -> PageBrief:
    prompt = build_prompt(url, html)
    classify = await run_agent(classify_agent, prompt)
    category = (classify.final_output.category or 'other').lower()
    specialist = SPECIALISTS.get(category, general_agent)
    # Specialist gets full HTML via context so extract_links sees the whole page.
    result = await run_agent(specialist, prompt, PageContext(html=html))
    return result.final_output


@task(max_concurrent=4)
async def analyze_page(url: str) -> PageBrief:
    get_logger().info('analyze %s', url)
    html = await fetch_page(url)
    brief = await summarize(url, html)
    log_brief(url, brief)
    return brief


### DISTRIBUTED RUN
# Two processes share a Redis queue. Run both from the repo root:
#   Terminal 1:  python -m examples.web_analyst.worker   # serve forever
#   Terminal 2:  python -m examples.web_analyst          # submit jobs


TASK_TYPES = [extract_links, run_agent, fetch_page, summarize, analyze_page]


async def register_task_types() -> None:
    # Create each @task type's DB row once, serially, under a lock so concurrent
    # first-time runs never race to insert the same row.
    async with RedisSemaphore(name='web_analyst:register_task_types', max_leases=1, ttl=60):
        async with async_session_scope() as session:
            for task_type in TASK_TYPES:
                await upsert_task_type_state(session, task_type)


@task
async def run_web_analyst_pipeline(urls: list[str]) -> list[PageBrief]:
    await register_task_types()
    print('Pipeline started...' + '\n' + 'Check logs in the filament UI for progress.')
    logger = get_logger()
    logger.info('Submitting %d url(s) to the queue …', len(urls))
    runs = await asyncio.gather(*(analyze_page.request(url) for url in urls))
    results = await asyncio.gather(*runs)
    logger.info('Runs complete.Run it again — summaries come straight from the cache.')
    # Queue results cross Redis as plain dicts (JSON round-trip), so rebuild the model.
    return [PageBrief.model_validate(r) for r in results]


def log_brief(url: str, b: PageBrief) -> None:
    # One message so the brief lands as a single log entry tied to the current run.
    payload = {'url': url, 'model': MODEL, **b.model_dump()}
    get_logger().info(json.dumps(payload, indent=2, ensure_ascii=False))


DEFAULT_URLS = [
    'https://news.ycombinator.com',
    'https://lite.cnn.com',
    'https://text.npr.org',
    'https://docs.python.org/3/',
    'https://fastapi.tiangolo.com',
    'https://react.dev',
    'https://peps.python.org/pep-0008/',
    'https://www.rfc-editor.org/rfc/rfc9110.html',
    'https://simonwillison.net',
    'https://example.com',
]


async def test_run_web_analyst_pipeline() -> None:
    briefs = await run_web_analyst_pipeline(DEFAULT_URLS)
    assert briefs and briefs[0].title
