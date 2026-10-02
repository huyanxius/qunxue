"""Bounded, revision-qualified response cache for public frontier projections only."""

import asyncio
from collections import OrderedDict
from hashlib import sha256

from fastapi import Request, Response
from fastapi.routing import APIRoute

from qunxue_api.modules.frontier_knowledge import frontier_today

_PUBLIC_PATHS = {
    "/api/frontier/summaries",
    "/api/frontier/search",
    "/api/frontier/topics",
    "/api/frontier/trends",
    "/api/frontier/sources",
    "/api/frontier/overview",
    "/api/frontier/calendar",
    "/api/frontier/period-report",
}
_MAX_ENTRIES = 64
_MAX_BYTES = 32 * 1024 * 1024


class FrontierPublicReadRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def cached(request: Request):
            if request.url.path not in _PUBLIC_PATHS:
                return await handler(request)
            store = getattr(request.app.state, "frontier_store", None)
            revision_reader = getattr(store, "read_revision", None)
            if revision_reader is None:
                return await handler(request)
            # Keep locks/cache within the app event loop, never global across apps.
            state = request.app.state
            if not hasattr(state, "frontier_public_cache"):
                state.frontier_public_cache = OrderedDict()
                state.frontier_public_cache_locks = {}
            revision = await asyncio.to_thread(revision_reader)
            key = (
                revision,
                frontier_today().isoformat(),
                request.url.path,
                tuple(sorted(request.query_params.multi_items())),
            )
            cache = state.frontier_public_cache
            lock = state.frontier_public_cache_locks.setdefault(request.url.path, asyncio.Lock())
            async with lock:
                value = cache.get(key)
                if value is None:
                    response = await handler(request)
                    if response.status_code != 200:
                        return response
                    body = response.body
                    etag = '"' + sha256(body).hexdigest() + '"'
                    value = (body, etag)
                    # Never publish a payload under a revision that changed mid-read.
                    after = await asyncio.to_thread(revision_reader)
                    if after == revision and len(body) <= _MAX_BYTES:
                        cache[key] = value
                        while (
                            len(cache) > _MAX_ENTRIES
                            or sum(len(v[0]) for v in cache.values()) > _MAX_BYTES
                        ):
                            cache.popitem(last=False)
                else:
                    cache.move_to_end(key)
            body, etag = value
            # Browser conditional reuse; do not enable broad CDN caching or serve stale
            # withdrawals. Every request checks the committed database revision.
            headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
            matches = [
                tag.strip().removeprefix("W/")
                for tag in request.headers.get("if-none-match", "").split(",")
            ]
            if etag in matches or "*" in matches:
                return Response(status_code=304, headers=headers)
            return Response(content=body, media_type="application/json", headers=headers)

        return cached
