"""API Router for Order Comments (Digitale Post-its)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User, UserRole
from goldsmith_erp.models.order_comment import OrderCommentCreate, OrderCommentUpdate, OrderCommentRead
from goldsmith_erp.services.comment_service import CommentService
from goldsmith_erp.core.permissions import Permission, require_permission

router = APIRouter()


@router.get("/orders/{order_id}/comments", response_model=List[OrderCommentRead])
@require_permission(Permission.ORDER_VIEW)
async def list_comments(
    order_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Alle Kommentare fuer einen Auftrag."""
    comments = await CommentService.get_comments_for_order(db, order_id, skip, limit)
    result = []
    for c in comments:
        comment_dict = {
            "id": c.id,
            "order_id": c.order_id,
            "user_id": c.user_id,
            "text": c.text,
            "user_name": None,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        if c.user:
            comment_dict["user_name"] = f"{c.user.first_name} {c.user.last_name}"
        result.append(OrderCommentRead(**comment_dict))
    return result


@router.post("/orders/{order_id}/comments", response_model=OrderCommentRead, status_code=201)
@require_permission(Permission.ORDER_VIEW)
async def create_comment(
    order_id: int,
    comment_in: OrderCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Neuen Kommentar zu einem Auftrag hinzufuegen."""
    comment = await CommentService.create_comment(db, order_id, current_user.id, comment_in)
    return OrderCommentRead(
        id=comment.id,
        order_id=comment.order_id,
        user_id=comment.user_id,
        text=comment.text,
        user_name=f"{current_user.first_name} {current_user.last_name}",
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.put("/orders/{order_id}/comments/{comment_id}", response_model=OrderCommentRead)
async def update_comment(
    order_id: int,
    comment_id: int,
    comment_in: OrderCommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Eigenen Kommentar bearbeiten."""
    comment = await CommentService.update_comment(db, comment_id, current_user.id, comment_in)
    if not comment:
        raise HTTPException(status_code=404, detail="Kommentar nicht gefunden oder keine Berechtigung")
    return OrderCommentRead(
        id=comment.id,
        order_id=comment.order_id,
        user_id=comment.user_id,
        text=comment.text,
        user_name=f"{current_user.first_name} {current_user.last_name}",
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.delete("/orders/{order_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    order_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kommentar loeschen (eigene oder als Admin alle)."""
    is_admin = current_user.role == UserRole.ADMIN
    deleted = await CommentService.delete_comment(db, comment_id, current_user.id, is_admin)
    if not deleted:
        raise HTTPException(status_code=404, detail="Kommentar nicht gefunden oder keine Berechtigung")
