"""HTTP API for Event Ledger — deployed to Cloud Run.

Uses Firebase ID token auth for all authenticated endpoints.
Page-scoped endpoints manage memories per page; user endpoints manage
page ownership and invites.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import firestore_storage
import page_storage
from committer import commit_memory_firestore, commit_memory_firestore_stream
from dates import today as _today, resolve_tz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Event Ledger API")

# Mount API v2 router (workspaces, series, occurrences, check-ins)
from api_v2 import router as v2_router  # noqa: E402
app.include_router(v2_router)


class StripApiPrefixMiddleware:
    """Allow Firebase Hosting /api/** rewrites without requiring separate routes.

    Firebase Hosting forwards requests to Cloud Run with the original path, e.g.
    `/api/pages/foo`. The backend historically serves `/pages/foo`.

    This middleware strips a leading `/api` prefix so both paths work.
    """

    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if path == "/api":
                scope = dict(scope)
                scope["path"] = "/"
            elif path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[len("/api"):]
        await self.inner_app(scope, receive, send)


# Must be installed before routing.
app.add_middleware(StripApiPrefixMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)

    extra = {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }

    trace_header = request.headers.get("x-cloud-trace-context")
    if trace_header:
        extra["trace"] = trace_header.split("/")[0]

    logger.info("request %s %s %d %.1fms", extra["method"], extra["path"],
                extra["status_code"], duration_ms, extra=extra)
    return response


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _verify_firebase_token(authorization: str = Header(...)) -> dict:
    """Verify a Firebase ID token and return the decoded token dict.

    The token dict contains at least ``uid``, ``email``, etc.
    Cloud Run uses Application Default Credentials (service account) to verify.

    During testing, set FIREBASE_AUTH_EMULATOR_HOST or pass a mock.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[len("Bearer "):]

    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        # Ensure Firebase Admin is initialized (required for verify_id_token).
        if not firebase_admin._apps:
            firebase_admin.initialize_app()

        decoded = firebase_auth.verify_id_token(token)
    except ImportError as exc:
        logger.error("firebase_admin_not_installed: %s", exc)
        raise HTTPException(status_code=500, detail="Firebase Admin not configured")
    except Exception as exc:
        logger.warning("firebase_auth_failure: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid Firebase token")
    return decoded


def _get_uid(token: dict = Depends(_verify_firebase_token)) -> str:
    """Extract uid from a verified Firebase token."""
    return token["uid"]


def _require_page_owner(slug: str, uid: str) -> page_storage.Page:
    """Fetch a page and verify the user is an owner. Raises 404 or 403."""
    page = page_storage.get_page(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    if uid not in page.owner_uids:
        raise HTTPException(status_code=403, detail="Not an owner of this page")
    return page


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

def _page_response(page: page_storage.Page) -> dict:
    """Build a JSON-serialisable dict for a Page."""
    return {**page.to_dict(), "slug": page.slug}


class CreateMemoryRequest(BaseModel):
    message: str
    attachments: list[str] | None = None
    visibility: str = "public"


class CreatePageRequest(BaseModel):
    slug: str
    title: str
    visibility: str = "public"
    description: str | None = None
    timezone: str | None = None


class UpdatePageRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    timezone: str | None = None


class CreateInviteRequest(BaseModel):
    role: str = "owner"  # "owner" grants co-owner access; "member" grants read-only access


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/_healthz")
@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------------------------------------------------------------------
# User endpoints (Firebase Auth)
# ---------------------------------------------------------------------------

@app.get("/users/me")
def get_current_user(uid: str = Depends(_get_uid)):
    user = page_storage.get_or_create_user(uid)
    return {"user": user.to_dict()}


@app.get("/users/me/pages")
def list_my_pages(uid: str = Depends(_get_uid)):
    pages = page_storage.list_pages_for_user(uid)
    return {
        "pages": [
            _page_response(p)
            for p in pages
        ],
    }


# ---------------------------------------------------------------------------
# Page endpoints (Firebase Auth)
# ---------------------------------------------------------------------------

@app.post("/pages")
def create_page(body: CreatePageRequest, uid: str = Depends(_get_uid)):
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except (KeyError, ZoneInfoNotFoundError):
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {body.timezone}")
    page = page_storage.Page(
        slug=body.slug,
        title=body.title,
        visibility=body.visibility,
        owner_uids=[uid],
        description=body.description,
        timezone=body.timezone,
    )
    try:
        created = page_storage.create_page(page)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Auto-set default_personal_page_id if this is a personal page
    if body.visibility == "personal":
        user = page_storage.get_user(uid)
        if user is None or user.default_personal_page_id is None:
            page_storage.get_or_create_user(uid)
            page_storage.update_user(uid, {"default_personal_page_id": body.slug})

    logger.info("create_page slug=%s uid=%s", body.slug, uid)
    return {"page": _page_response(created)}


@app.get("/pages/{slug}")
def get_page(slug: str, authorization: str = Header(default=None)):
    """Get page metadata. Public pages are readable by anyone; personal pages require owner auth."""
    page = page_storage.get_page(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.visibility == "public":
        return {"page": _page_response(page)}

    # Personal page — require auth
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = _verify_firebase_token(authorization)
    uid = token["uid"]
    if uid not in page.owner_uids and uid not in page.member_uids:
        raise HTTPException(status_code=403, detail="Not an owner of this page")
    return {"page": _page_response(page)}


@app.patch("/pages/{slug}")
def update_page(slug: str, body: UpdatePageRequest, uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "timezone" in updates:
        try:
            ZoneInfo(updates["timezone"])
        except (KeyError, ZoneInfoNotFoundError):
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {updates['timezone']}")
    try:
        updated = page_storage.update_page(slug, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    page_storage.write_audit_log(
        page_slug=slug, action="page_updated", actor_uid=uid,
        metadata={"fields": list(updates.keys())},
    )
    return {"page": _page_response(updated)}


@app.delete("/pages/{slug}", response_model=None)
def delete_page(slug: str, uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    page_storage.soft_delete_page(slug)
    page_storage.write_audit_log(
        page_slug=slug, action="page_deleted", actor_uid=uid,
    )
    return {"ok": True}


@app.post("/pages/{slug}/restore")
def restore_page(slug: str, uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    try:
        page = page_storage.restore_page(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    page_storage.write_audit_log(
        page_slug=slug, action="page_restored", actor_uid=uid,
    )
    return {"page": _page_response(page)}


@app.delete("/pages/{slug}/owners/{target_uid}")
def remove_page_owner(slug: str, target_uid: str, uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    try:
        updated = page_storage.remove_owner(slug, target_uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    page_storage.write_audit_log(
        page_slug=slug,
        action="owner_removed",
        actor_uid=uid,
        target_uid=target_uid,
    )
    logger.info("remove_owner slug=%s actor=%s target=%s", slug, uid, target_uid)
    return {"page": _page_response(updated)}


# ---------------------------------------------------------------------------
# Invite endpoints (Firebase Auth)
# ---------------------------------------------------------------------------

@app.post("/pages/{slug}/invites")
def create_invite(slug: str, body: CreateInviteRequest = CreateInviteRequest(), uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    try:
        invite = page_storage.create_invite(slug, uid, role=body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    page_storage.write_audit_log(
        page_slug=slug,
        action="invite_created",
        actor_uid=uid,
        metadata={"invite_id": invite.invite_id, "role": invite.role},
    )
    logger.info("create_invite slug=%s uid=%s invite_id=%s role=%s", slug, uid, invite.invite_id, invite.role)
    return {"invite": invite.to_dict(), "page_slug": slug}


@app.post("/invites/{invite_id}/accept")
def accept_invite(invite_id: str, uid: str = Depends(_get_uid)):
    try:
        invite = page_storage.accept_invite(invite_id, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("accept_invite invite_id=%s uid=%s page=%s", invite_id, uid, invite.page_slug)
    return {"ok": True, "page_slug": invite.page_slug}


# ---------------------------------------------------------------------------
# Page-scoped memory endpoints (Firebase Auth)
# ---------------------------------------------------------------------------

@app.post("/pages/{slug}/memories")
def create_page_memory(slug: str, body: CreateMemoryRequest, uid: str = Depends(_get_uid)):
    page = _require_page_owner(slug, uid)
    page_tz = resolve_tz(page.timezone)
    try:
        result = commit_memory_firestore(
            message=body.message,
            today=_today(tz=page_tz),
            attachment_urls=body.attachments,
            page_id=slug,
            visibility=body.visibility,
        )
    except Exception:
        logger.exception("create_page_memory failed slug=%s uid=%s", slug, uid)
        raise HTTPException(status_code=502, detail="Failed to process memory — the AI backend returned an invalid response. Please try again.")
    logger.info(
        "create_page_memory slug=%s count=%d", slug, len(result),
    )
    return {
        "memories": [
            {"action": r.action, "id": r.doc_id, "memory": r.memory.to_dict()}
            for r in result
        ],
    }


@app.post("/pages/{slug}/memories/stream")
def create_page_memory_stream(slug: str, body: CreateMemoryRequest, uid: str = Depends(_get_uid)):
    """Like POST /memories but streams SSE status events while the AI processes the message.

    Each event is a JSON line prefixed with ``data: ``.  The final event has
    ``type == "done"`` and includes the committed memories.
    """
    page = _require_page_owner(slug, uid)
    page_tz = resolve_tz(page.timezone)

    def generate():
        try:
            for event in commit_memory_firestore_stream(
                message=body.message,
                today=_today(tz=page_tz),
                attachment_urls=body.attachments,
                page_id=slug,
                visibility=body.visibility,
            ):
                if event["type"] == "done":
                    memories = [
                        {"action": r.action, "id": r.doc_id, "memory": r.memory.to_dict()}
                        for r in event["results"]
                    ]
                    yield f"data: {json.dumps({'type': 'done', 'memories': memories})}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("create_page_memory_stream failed slug=%s uid=%s", slug, uid)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to process memory — please try again.'})}\n\n"

    logger.info("create_page_memory_stream slug=%s uid=%s", slug, uid)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/pages/{slug}/memories")
def list_page_memories(slug: str, authorization: str = Header(default=None)):
    """List memories for a page. Public pages readable by anyone; personal pages require owner auth.

    Members-only memories (visibility="members") are filtered out for non-owners.
    """
    page = page_storage.get_page(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    is_owner = False
    is_member = False
    if page.visibility == "personal":
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")
        token = _verify_firebase_token(authorization)
        uid = token["uid"]
        if uid in page.owner_uids:
            is_owner = True
        elif uid in page.member_uids:
            is_member = True
        else:
            raise HTTPException(status_code=403, detail="Not an owner of this page")
    elif authorization:
        try:
            token = _verify_firebase_token(authorization)
            uid = token["uid"]
            if uid in page.owner_uids:
                is_owner = True
            elif uid in page.member_uids:
                is_member = True
        except HTTPException:
            pass

    page_tz = resolve_tz(page.timezone)
    pairs = firestore_storage.load_memories_by_page(slug, _today(tz=page_tz))

    if is_owner:
        pass  # owners see all memories
    elif is_member:
        pairs = [(doc_id, mem) for doc_id, mem in pairs if mem.visibility in ("public", "members")]
    else:
        pairs = [(doc_id, mem) for doc_id, mem in pairs if mem.visibility == "public"]

    return {
        "memories": [
            {"id": doc_id, **mem.to_dict()}
            for doc_id, mem in pairs
        ],
    }


@app.delete("/pages/{slug}/memories/{memory_id}")
def delete_page_memory(slug: str, memory_id: str, uid: str = Depends(_get_uid)):
    _require_page_owner(slug, uid)
    # Verify the memory belongs to this page
    mem = firestore_storage.get_memory(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if mem.page_id != slug:
        raise HTTPException(status_code=404, detail="Memory not found on this page")
    firestore_storage.delete_memory(memory_id)
    logger.info("delete_page_memory slug=%s memory_id=%s uid=%s", slug, memory_id, uid)
    return {"ok": True}
