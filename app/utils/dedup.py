from cachetools import TTLCache

# In-memory cache: stores message IDs seen in the last 5 minutes
# This provides fast dedup for webhook retries. DB check provides durable dedup.
_seen_messages: TTLCache = TTLCache(maxsize=10000, ttl=300)


def is_duplicate(message_id: str) -> bool:
    if message_id in _seen_messages:
        return True
    _seen_messages[message_id] = True
    return False
