"""Agent registration and token issue.

Two gates: reading the roster takes a viewer credential, but everything that
touches tokens — create, rotate, delete — takes the admin session. Whoever
owns Agent Notifications decides which agents may write to it, and a viewer
token must never be able to promote itself into a write credential."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import generate_token, get_db, hash_token, require_admin, require_viewer
from ..db.models import Agent
from ..errors import problem
from ..schemas import AgentCreated, AgentIn, AgentOut

router = APIRouter(prefix="/api/v1/agents", tags=["agents"],
                   dependencies=[Depends(require_viewer)])


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "agent"


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.scalars(select(Agent).order_by(Agent.created_at)).all()


@router.post("", response_model=AgentCreated, status_code=201,
             dependencies=[Depends(require_admin)])
def create_agent(data: AgentIn, db: Session = Depends(get_db)):
    slug = slugify(data.name)
    exists = db.scalar(select(Agent).where((Agent.name == data.name) | (Agent.slug == slug)))
    if exists:
        raise problem(409, "Agent exists", f"An agent named '{data.name}' is already registered.")
    token = generate_token()
    agent = Agent(name=data.name, slug=slug, token_hash=hash_token(token))
    db.add(agent)
    db.commit()
    # The raw token exists only in this response; only its hash is stored.
    return AgentCreated(id=agent.id, name=agent.name, slug=agent.slug,
                        created_at=agent.created_at, last_seen_at=None, token=token)


@router.post("/{slug}/token", response_model=AgentCreated,
             dependencies=[Depends(require_admin)])
def rotate_token(slug: str, db: Session = Depends(get_db)):
    """Issue a fresh token, invalidating the old one.

    Only the hash is stored, so a token cannot be re-shown — and an install
    screen that only works in the seconds after registration is not an install
    screen. Rotating is the honest way to recover a usable credential, and it
    revives a previously revoked agent by design: re-connecting a harness you
    turned off should not require losing its notification history.
    """
    agent = db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is None:
        raise problem(404, "Not found", f"No agent with slug '{slug}'.")
    token = generate_token()
    agent.token_hash = hash_token(token)
    db.commit()
    return AgentCreated(id=agent.id, name=agent.name, slug=agent.slug,
                        created_at=agent.created_at, last_seen_at=agent.last_seen_at,
                        token=token)


@router.delete("/{slug}", status_code=204,
               dependencies=[Depends(require_admin)])
def delete_agent(slug: str, db: Session = Depends(get_db)):
    agent = db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is None:
        raise problem(404, "Not found", f"No agent with slug '{slug}'.")
    # Revoking access ≠ erasing history: the token dies, notifications stay.
    agent.token_hash = "revoked:" + agent.id
    db.commit()
    return Response(status_code=204)
