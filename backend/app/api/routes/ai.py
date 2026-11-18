from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models import AIConversation, AIMessage
from app.services import ai
from app.services.common import audit, get_or_404

router = APIRouter(prefix="/ai", tags=["AI Assistant"])
use = require("ai.use")

SUGGESTIONS = {
    "common": ["What is my leave balance?", "Which of my tasks are overdue?", "What holidays are coming up?"],
    "attendance.view_all": ["Summarise attendance for this month", "Who was late most often this month?"],
    "projects": ["Which projects are delayed and why?", "Summarise progress across active projects"],
    "employees.view_all": ["Give me a workforce overview by department"],
    "clients.view": ["Summarise recent communication with our top client"],
    "payroll.view": ["Compare payroll totals month by month this year"],
}


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


@router.get("/status")
def status(current: CurrentUser = Depends(use)):
    s = list(SUGGESTIONS["common"])
    for k in ("attendance.view_all", "employees.view_all", "clients.view", "payroll.view"):
        if current.has(k):
            s += SUGGESTIONS[k]
    s += SUGGESTIONS["projects"]
    return {"configured": ai.ai_configured(), "suggestions": s[:8]}


@router.get("/conversations")
def conversations(current: CurrentUser = Depends(use), db: Session = Depends(get_db)):
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in db.scalars(
        select(AIConversation).where(AIConversation.user_id == current.id).order_by(AIConversation.updated_at.desc()).limit(50))]


@router.get("/conversations/{cid}")
def conversation(cid: int, current: CurrentUser = Depends(use), db: Session = Depends(get_db)):
    c = get_or_404(db, AIConversation, cid, "Conversation")
    if c.user_id != current.id:
        raise HTTPException(404, "Conversation not found")
    return {"id": c.id, "title": c.title, "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at}
                                                       for m in db.scalars(select(AIMessage).where(AIMessage.conversation_id == cid).order_by(AIMessage.id))]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, current: CurrentUser = Depends(use), db: Session = Depends(get_db)):
    c = get_or_404(db, AIConversation, cid, "Conversation")
    if c.user_id != current.id:
        raise HTTPException(404, "Conversation not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/chat")
@limiter.limit("20/minute")
def ask(request: Request, body: AskIn, current: CurrentUser = Depends(use), db: Session = Depends(get_db)):
    if body.conversation_id:
        conv = get_or_404(db, AIConversation, body.conversation_id, "Conversation")
        if conv.user_id != current.id:
            raise HTTPException(404, "Conversation not found")
    else:
        conv = None
    history = []
    if conv:
        history = [{"role": m.role, "content": m.content} for m in db.scalars(
            select(AIMessage).where(AIMessage.conversation_id == conv.id).order_by(AIMessage.id))]
    answer = ai.chat(db, current, history, body.message)
    if not conv:
        conv = AIConversation(user_id=current.id, title=body.message[:120])
        db.add(conv)
        db.flush()
    db.add_all([AIMessage(conversation_id=conv.id, role="user", content=body.message),
                AIMessage(conversation_id=conv.id, role="model", content=answer)])
    conv.title = conv.title or body.message[:120]
    audit(db, current.user, "ai.query", "ai_conversation", conv.id, body.message[:200])
    db.commit()
    return {"conversation_id": conv.id, "answer": answer}
