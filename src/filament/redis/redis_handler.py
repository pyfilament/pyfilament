import json
import logging

from filament.redis.redis_utils import r_sync

logger = logging.getLogger(__name__)

MAX_LOGS_TTL = 3600 * 24 * 14


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_dict = {
            'timestamp': record.created,
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
        }
        return json.dumps(log_dict, default=str, separators=(',', ':'))


class RedisHandler(logging.Handler):
    def __init__(self, key_prefix='filament_log'):
        super().__init__()
        self.redis = r_sync
        self.key_prefix = key_prefix

    def emit(self, record):
        try:
            msg = self.format(record)
            redis_key = f'{self.key_prefix}:{record.name}'
            self.redis.rpush(redis_key, msg)
            self.redis.expire(redis_key, MAX_LOGS_TTL)
        except Exception:
            self.handleError(record)
