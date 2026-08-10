"""Operational endpoints. Viewer-gated: whoever can read the feed may run them.

`POST /api/v1/prune` exists for deployments where the in-process daily loop
never fires — serverless instances freeze between requests — so an external
cron (Vercel Cron, GitHub Actions, crontab) triggers retention over HTTP with
a viewer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import get_db, require_viewer
from ..core.retention import prune

router = APIRouter(prefix="/api/v1", tags=["admin"],
                   dependencies=[Depends(require_viewer)])


# GET as well as POST: Vercel Cron only makes GET requests, attaching
# `Authorization: Bearer $CRON_SECRET` — set CRON_SECRET to a viewer token and
# the normal viewer gate applies. POST remains the canonical form.
@router.api_route("/prune", methods=["POST", "GET"])
def run_prune(request: Request, db: Session = Depends(get_db)):
    deleted = prune(db, request.app.state.settings.retention_days)
    return {"deleted": deleted}
