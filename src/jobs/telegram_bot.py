"""Standalone Telegram bot runner.

Run as:
    python -m src.jobs.telegram_bot

Deprecated: this runner uses the legacy `channels.telegram.TelegramAdapter`
flow. The current product uses per-room Telegram bots configured through
`POST /v2/rooms/{room_id}/telegram-bot`.

Uses long-polling (getUpdates) so no public webhook URL is required
during local development or testing.

Set TELEGRAM_BOT_TOKEN in the environment before starting.

For production: use the per-room webhook registration flow instead.
"""

from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)


def run_polling() -> None:
    try:
        import httpx
    except ImportError:
        print("httpx is required: pip install httpx", file=sys.stderr)
        sys.exit(1)

    from channels.telegram import TelegramAdapter

    adapter = TelegramAdapter()
    logger.info("Telegram bot polling started")

    offset = 0
    token = adapter.token
    api = "https://api.telegram.org/bot" + token

    while True:
        try:
            resp = httpx.get(
                api + "/getUpdates",
                params={"timeout": 30, "offset": offset},
                timeout=35,
            )
            if not resp.is_success:
                logger.error("getUpdates failed: %s", resp.text)
                time.sleep(5)
                continue
            data = resp.json()
            for update in data.get("result", []):
                update_id = update.get("update_id", 0)
                offset = update_id + 1
                try:
                    adapter.dispatch(update)
                except Exception as exc:
                    logger.exception("Error dispatching update %d: %s", update_id, exc)
        except KeyboardInterrupt:
            logger.info("Shutting down bot")
            break
        except Exception as exc:
            logger.error("Polling error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_polling()
