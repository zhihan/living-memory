from __future__ import annotations
import os, logging
from typing import Any
try:
    import httpx
except ImportError:
    httpx = None
from .base import ChannelAdapter, IncomingMessage, OutgoingMessage, ParsedCommand
logger = logging.getLogger(__name__)
_API = "https://api.telegram.org/bot{token}/{method}"

def _api_url(token, method):
    return _API.format(token=token, method=method)


class TelegramAdapter(ChannelAdapter):
    def __init__(self, token=None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self.token: raise ValueError("TELEGRAM_BOT_TOKEN not set")

    def send_message(self, msg):
        if httpx is None: raise RuntimeError("httpx required")
        url = _api_url(self.token, "sendMessage")
        payload = {"chat_id": msg.recipient_id, "text": msg.text, "parse_mode": "HTML"}
        payload.update(msg.extra)
        try:
            r = httpx.post(url, json=payload, timeout=10)
            if not r.is_success: logger.error("sendMessage failed: %s", r.text)
        except Exception as e: logger.error("Telegram error: %s", e)

    def parse_incoming(self, raw):
        m = raw.get("message") or raw.get("edited_message")
        if m is None: return None
        text = m.get("text", "")
        if not text: return None
        sid = str((m.get("chat") or {}).get("id") or (m.get("from") or {}).get("id", ""))
        return IncomingMessage(channel="telegram", sender_id=sid, text=text, raw=raw)

    def handle_command(self, command, incoming):
        handlers = {"start": self._start, "meetings": self._meetings, "next": self._next, "confirm": self._confirm}
        h = handlers.get(command.command)
        if h is None: return OutgoingMessage(recipient_id=incoming.sender_id, text="Unknown command. Try /start")
        return h(command, incoming)

    def _start(self, cmd, inc):
        return OutgoingMessage(recipient_id=inc.sender_id, text="Welcome to Small Group!" + chr(92) + "n/meetings /next /confirm <id>")

    def _meetings(self, cmd, inc):
        occs = self._fetch_occurrences(inc.sender_id)
        if not occs: return OutgoingMessage(recipient_id=inc.sender_id, text="No upcoming meetings.")
        lines = ["Upcoming meetings:"]
        for o in occs[:5]: lines.append("- " + o.get("scheduled_for","?") + ": " + o.get("title","Untitled"))
        return OutgoingMessage(recipient_id=inc.sender_id, text=chr(10).join(lines))

    def _next(self, cmd, inc):
        occs = self._fetch_occurrences(inc.sender_id)
        if not occs: return OutgoingMessage(recipient_id=inc.sender_id, text="No upcoming occurrences.")
        o = occs[0]
        text = "Next: " + o.get("title","Untitled") + chr(10) + "When: " + o.get("scheduled_for","?") + chr(10) + "ID: " + o.get("occurrence_id","?")
        return OutgoingMessage(recipient_id=inc.sender_id, text=text)

    def _confirm(self, cmd, inc):
        if not cmd.args: return OutgoingMessage(recipient_id=inc.sender_id, text="Usage: /confirm <occurrence_id>")
        oid = cmd.args[0]
        ok = self._post_check_in(inc.sender_id, oid)
        m = "Checked in! Great work." if ok else "Could not check in to " + oid + ". Check the ID."
        return OutgoingMessage(recipient_id=inc.sender_id, text=m)

    def _fetch_occurrences(self, sender_id):
        # TODO: resolve sender_id -> workspace, call GET /v2/workspaces/{id}/occurrences
        return []

    def _post_check_in(self, sender_id, occurrence_id):
        # TODO: resolve sender_id -> uid, call POST /v2/occurrences/{id}/check-ins
        return False
