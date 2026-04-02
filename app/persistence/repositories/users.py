from __future__ import annotations

from sqlalchemy import and_, case, func, select

from app.domain.enums import UserStatus
from app.persistence.models import User
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()

    def get_dashboard_counts(self) -> dict[str, int]:
        statement = select(
            func.count(User.id),
            func.sum(case((and_(User.status == UserStatus.ACTIVE, User.is_active.is_(True)), 1), else_=0)),
            func.sum(case((User.status == UserStatus.BLOCKED, 1), else_=0)),
        )
        total_users, active_users, blocked_users = self.session.execute(statement).one()
        return {
            "total_users": int(total_users or 0),
            "active_users": int(active_users or 0),
            "blocked_users": int(blocked_users or 0),
        }
