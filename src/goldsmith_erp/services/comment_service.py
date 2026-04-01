"""Service for Order Comments (Digitale Post-its)."""
import logging
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    NotificationSeverityEnum,
    NotificationTypeEnum,
    OrderComment as CommentModel,
    User as UserModel,
    UserRole,
)
from goldsmith_erp.models.order_comment import OrderCommentCreate, OrderCommentUpdate

logger = logging.getLogger(__name__)


class CommentService:
    @staticmethod
    async def get_comments_for_order(
        db: AsyncSession,
        order_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> List[CommentModel]:
        result = await db.execute(
            select(CommentModel)
            .where(CommentModel.order_id == order_id)
            .options(selectinload(CommentModel.user))
            .order_by(CommentModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def create_comment(
        db: AsyncSession,
        order_id: int,
        user_id: int,
        comment_in: OrderCommentCreate
    ) -> CommentModel:
        comment = CommentModel(
            order_id=order_id,
            user_id=user_id,
            text=comment_in.text
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)

        # Fire comment notifications after the comment is durably committed.
        # Import lazily to avoid circular imports (notification_service imports
        # from db.models, which is safe, but the service graph is complex).
        try:
            from goldsmith_erp.services.notification_service import NotificationService

            # Resolve the author's display name for the notification message.
            author_result = await db.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            author = author_result.scalar_one_or_none()
            if author and (author.first_name or author.last_name):
                author_name = f"{author.first_name or ''} {author.last_name or ''}".strip()
            else:
                author_name = f"Benutzer #{user_id}"

            # Truncate comment preview to 100 chars, add ellipsis if needed.
            preview = comment_in.text[:100]
            if len(comment_in.text) > 100:
                preview += "..."

            title = f"Neuer Kommentar: Auftrag #{order_id}"
            message = f"{author_name} hat einen Kommentar hinterlassen: {preview}"

            # Notify all active ADMIN and GOLDSMITH users except the author.
            recipients_result = await db.execute(
                select(UserModel).where(
                    and_(
                        UserModel.is_active.is_(True),
                        UserModel.role.in_([UserRole.ADMIN, UserRole.GOLDSMITH]),
                        UserModel.id != user_id,
                    )
                )
            )
            recipients = recipients_result.scalars().all()

            for recipient in recipients:
                await NotificationService.create_notification(
                    db=db,
                    user_id=recipient.id,
                    title=title,
                    message=message,
                    notification_type=NotificationTypeEnum.COMMENT,
                    severity=NotificationSeverityEnum.INFO,
                    related_order_id=order_id,
                )

        except Exception:
            # Notification failure must not affect the comment that was
            # already committed.  Log the full traceback for debugging.
            logger.exception(
                "Failed to fire comment notifications",
                extra={"order_id": order_id, "user_id": user_id, "comment_id": comment.id},
            )

        return comment

    @staticmethod
    async def update_comment(
        db: AsyncSession,
        comment_id: int,
        order_id: int,
        user_id: int,
        comment_in: OrderCommentUpdate
    ) -> Optional[CommentModel]:
        result = await db.execute(
            select(CommentModel).where(
                CommentModel.id == comment_id,
                CommentModel.order_id == order_id,
                CommentModel.user_id == user_id
            )
        )
        comment = result.scalar_one_or_none()
        if not comment:
            return None
        if comment_in.text is not None:
            comment.text = comment_in.text
        await db.commit()
        await db.refresh(comment)
        return comment

    @staticmethod
    async def delete_comment(
        db: AsyncSession,
        comment_id: int,
        order_id: int,
        user_id: int,
        is_admin: bool = False
    ) -> bool:
        query = select(CommentModel).where(
            CommentModel.id == comment_id,
            CommentModel.order_id == order_id
        )
        if not is_admin:
            query = query.where(CommentModel.user_id == user_id)
        result = await db.execute(query)
        comment = result.scalar_one_or_none()
        if not comment:
            return False
        await db.delete(comment)
        await db.commit()
        return True
