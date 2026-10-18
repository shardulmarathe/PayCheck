"""FastAPI /check in front of Ollama, llama.cpp, or an in-process mock."""

from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from guardtrain.clients import mock_raw
from guardtrain.parse import parse_guard_output
from guardtrain.prompts import build_messages, estimate_tokens
from guardtrain.redact import redact
from guardtrain.schema import LabelRow

CompleteFn = Callable[[list[dict[str, str]]], tuple[str, int, int]]


class CheckIn(BaseModel):
    page_text: str = Field(..., min_length=1)
    page_id: str = ""
    store: str = ""


class CheckOut(BaseModel):
    verdict: str
    attack_type: str
    evidence: str
    instruction: str


def mock_complete(messages: list[dict[str, str]]) -> tuple[str, int, int]:
    user = messages[-1]["content"]
    raw = mock_raw(user)
    in_tok = sum(estimate_tokens(message["content"]) for message in messages)
    return raw, in_tok, estimate_tokens(raw)


def create_app(
    complete: CompleteFn,
    *,
    adapter: str = "json",
    max_page_tokens: int = 2000,
    backend_name: str = "mock",
) -> FastAPI:
    app = FastAPI(title="checkout-guard", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "backend": backend_name}

    @app.post("/check", response_model=CheckOut)
    def check(body: CheckIn) -> CheckOut:
        # Page text is not logged. Only the parsed contract is returned.
        row = LabelRow(
            page_id=body.page_id or "page",
            store=body.store,
            page_text=body.page_text,
        )
        messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
        try:
            raw, _in_tok, _out_tok = complete(messages)
        except Exception as exc:  # noqa: BLE001 - upstream failure, not a bad request
            raise HTTPException(
                status_code=502,
                detail={"error": "upstream", "message": redact(str(exc))[:300]},
            ) from None
        parsed = parse_guard_output(raw, adapter=adapter)
        if not parsed.parse_ok:
            raise HTTPException(
                status_code=422,
                detail={"error": "unparseable", "raw": redact(raw)[:500]},
            )
        return CheckOut(**parsed.as_dict())

    return app


def serve(app: FastAPI, port: int | None = None) -> None:
    import uvicorn

    bind_port = port if port is not None else int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=bind_port)
