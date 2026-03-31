"""Service for Order Comments (Digitale Post-its)."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from goldsmith_erp.db.models import OrderComment as CommentModel, User as UserModel
from goldsmith_erp.models.order_comment import OrderCommentCreate, OrderCommentUpdate


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
        return comment

    @staticmethod
    async def update_comment(
        db: AsyncSession,
        comment_id: int,
        user_id: int,
        comment_in: OrderCommentUpdate
    ) -> Optional[CommentModel]:
        result = await db.execute(
            select(CommentModel).where(
                CommentModel.id == comment_id,
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
        user_id: int,
        is_admin: bool = False
    ) -> bool:
        query = select(CommentModel).where(CommentModel.id == comment_id)
        if not is_admin:
            query = query.where(CommentModel.user_id == user_id)
        result = await db.execute(query)
        comment = result.scalar_one_or_none()
        if not comment:
            return False
        await db.delete(comment)
        await db.commit()
        return True
