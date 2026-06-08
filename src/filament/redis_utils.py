import logging
import os

from dotenv import load_dotenv
from redis import Redis as RedisSync
from redis.asyncio import Redis as RedisAsync

logger = logging.getLogger(__name__)

load_dotenv()
REDIS_HOST = os.getenv('FILAMENT_REDIS_HOST', 'localhost')
REDIS_PORT = os.getenv('FILAMENT_REDIS_PORT', 6379)
REDIS_DB = os.getenv('FILAMENT_REDIS_DB', 0)


r = RedisAsync(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True, socket_connect_timeout=10)
r_sync = RedisSync(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True, socket_connect_timeout=10)
