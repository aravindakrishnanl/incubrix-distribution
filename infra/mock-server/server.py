"""Minimal mock server for Discourse, Dev.to, and webhook targets.

Simulates the external platform APIs for local development and testing.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="IncuBrix Mock Platform Server")

# In-memory store: {post_id: post_data}
_posts: dict[str, dict] = {}
_post_counter = 0


def _next_id() -> str:
    global _post_counter
    _post_counter += 1
    return str(_post_counter)


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Discourse mock ─────────────────────────────────────────────────────────────
@app.post("/discourse/posts.json")
async def discourse_create_post(request: Request):
    body = await request.json()
    post_id = _next_id()
    _posts[f"discourse:{post_id}"] = body
    return {"id": int(post_id), "topic_id": int(post_id) + 1000, "raw": body.get("raw")}


@app.get("/discourse/posts/{post_id}.json")
def discourse_get_post(post_id: str):
    key = f"discourse:{post_id}"
    if key not in _posts:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"id": int(post_id), "topic_id": int(post_id) + 1000, "reads": 42, "like_count": 3, "reply_count": 1}


@app.delete("/discourse/posts/{post_id}.json")
def discourse_delete_post(post_id: str):
    _posts.pop(f"discourse:{post_id}", None)
    return {}


# ── Dev.to mock ───────────────────────────────────────────────────────────────
@app.post("/devto/articles")
async def devto_create_article(request: Request):
    body = await request.json()
    post_id = _next_id()
    article = body.get("article", {})
    _posts[f"devto:{post_id}"] = article
    return {
        "id": int(post_id),
        "url": f"http://localhost:8080/devto/articles/{post_id}",
        "published": True,
        **article,
    }


@app.get("/devto/articles/{post_id}")
def devto_get_article(post_id: str):
    key = f"devto:{post_id}"
    if key not in _posts:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {
        "id": int(post_id),
        "url": f"http://localhost:8080/devto/articles/{post_id}",
        "published": True,
        "page_views_count": 100,
        "positive_reactions_count": 10,
        "comments_count": 2,
    }


@app.put("/devto/articles/{post_id}")
async def devto_update_article(post_id: str, request: Request):
    body = await request.json()
    key = f"devto:{post_id}"
    if key in _posts:
        _posts[key].update(body.get("article", {}))
    return {"id": int(post_id), "published": body.get("article", {}).get("published", True)}


# ── Generic webhook target ─────────────────────────────────────────────────────
@app.post("/webhook")
async def webhook_target(request: Request):
    body = await request.json()
    post_id = _next_id()
    _posts[f"webhook:{post_id}"] = body
    return {"id": post_id, "received": True}
