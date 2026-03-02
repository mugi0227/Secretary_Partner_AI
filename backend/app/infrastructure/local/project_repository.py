"""
SQLite implementation of Project repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import aliased

from app.core.exceptions import NotFoundError
from app.infrastructure.local.database import (
    ProjectMemberORM,
    ProjectORM,
    TaskAssignmentORM,
    TaskORM,
    get_session_factory,
)
from app.interfaces.project_repository import IProjectRepository
from app.models.enums import ProjectStatus, ProjectVisibility, TaskStatus
from app.models.project import Project, ProjectCreate, ProjectUpdate, ProjectWithTaskCount


class SqliteProjectRepository(IProjectRepository):
    """SQLite implementation of project repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: ProjectORM) -> Project:
        """Convert ORM object to Pydantic model."""
        return Project(
            id=UUID(orm.id),
            user_id=orm.user_id,
            name=orm.name,
            description=orm.description,
            status=ProjectStatus(orm.status),
            visibility=ProjectVisibility(orm.visibility) if orm.visibility else ProjectVisibility.PRIVATE,
            context_summary=orm.context_summary,
            context=orm.context,
            priority=orm.priority if orm.priority is not None else 5,
            goals=orm.goals if orm.goals is not None else [],
            key_points=orm.key_points if orm.key_points is not None else [],
            kpi_config=orm.kpi_config,
            parent_project_id=UUID(orm.parent_project_id) if orm.parent_project_id else None,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(self, user_id: str, project: ProjectCreate) -> Project:
        """Create a new project."""
        async with self._session_factory() as session:
            kpi_config = project.kpi_config.model_dump() if project.kpi_config else None
            orm = ProjectORM(
                id=str(uuid4()),
                user_id=user_id,
                name=project.name,
                description=project.description,
                visibility=project.visibility.value,
                context_summary=project.context_summary,
                context=project.context,
                priority=project.priority,
                goals=project.goals,
                key_points=project.key_points,
                kpi_config=kpi_config,
                parent_project_id=str(project.parent_project_id) if project.parent_project_id else None,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, project_id: UUID) -> Optional[Project]:
        """Get a project by ID (accessible if user is owner, member, or member of ancestor)."""
        async with self._session_factory() as session:
            # Check if user is owner or member of this project
            result = await session.execute(
                select(ProjectORM)
                .outerjoin(
                    ProjectMemberORM,
                    ProjectORM.id == ProjectMemberORM.project_id
                )
                .where(
                    and_(
                        ProjectORM.id == str(project_id),
                        or_(
                            ProjectORM.user_id == user_id,
                            ProjectMemberORM.member_user_id == user_id,
                        ),
                    )
                )
                .distinct()
            )
            orm = result.scalars().first()
            if orm:
                return self._orm_to_model(orm)

            # Check if user is member of any ancestor project
            ancestor_cte = text("""
                WITH RECURSIVE ancestors AS (
                    SELECT parent_project_id FROM projects WHERE id = :project_id
                    UNION ALL
                    SELECT p.parent_project_id FROM projects p
                    INNER JOIN ancestors a ON p.id = a.parent_project_id
                    WHERE p.parent_project_id IS NOT NULL
                )
                SELECT parent_project_id FROM ancestors WHERE parent_project_id IS NOT NULL
            """)
            ancestor_result = await session.execute(
                ancestor_cte, {"project_id": str(project_id)}
            )
            ancestor_ids = [row[0] for row in ancestor_result.fetchall()]

            if ancestor_ids:
                # Check if user is a member of any ancestor project
                member_check = await session.execute(
                    select(ProjectMemberORM).where(
                        and_(
                            ProjectMemberORM.project_id.in_(ancestor_ids),
                            ProjectMemberORM.member_user_id == user_id,
                        )
                    )
                )
                if member_check.scalars().first():
                    # User has access via ancestor; fetch the project directly
                    proj_result = await session.execute(
                        select(ProjectORM).where(ProjectORM.id == str(project_id))
                    )
                    proj_orm = proj_result.scalars().first()
                    return self._orm_to_model(proj_orm) if proj_orm else None

            return None

    async def get_by_id(self, project_id: UUID) -> Optional[Project]:
        """Get a project by ID without user check (for system/background processes)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectORM).where(ProjectORM.id == str(project_id))
            )
            orm = result.scalars().first()
            return self._orm_to_model(orm) if orm else None

    async def list(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        top_level_only: bool = False,
    ) -> list[Project]:
        """List projects with optional filters (includes projects where user is owner or member)."""
        async with self._session_factory() as session:
            # Aliases for joining parent project and its members
            ParentProject = aliased(ProjectORM)
            ParentMember = aliased(ProjectMemberORM)

            # Select projects where user is owner, member,
            # OR child of a project the user owns/is a member of
            query = (
                select(ProjectORM)
                .outerjoin(
                    ProjectMemberORM,
                    ProjectORM.id == ProjectMemberORM.project_id
                )
                .outerjoin(
                    ParentProject,
                    ProjectORM.parent_project_id == ParentProject.id
                )
                .outerjoin(
                    ParentMember,
                    ParentProject.id == ParentMember.project_id
                )
                .where(
                    or_(
                        ProjectORM.user_id == user_id,
                        ProjectMemberORM.member_user_id == user_id,
                        ParentProject.user_id == user_id,
                        ParentMember.member_user_id == user_id,
                    )
                )
                .distinct()
            )

            if status:
                query = query.where(ProjectORM.status == status)

            if top_level_only:
                query = query.where(ProjectORM.parent_project_id.is_(None))

            query = query.order_by(ProjectORM.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def list_with_task_count(
        self,
        user_id: str,
        status: Optional[str] = None,
        top_level_only: bool = False,
    ) -> list[ProjectWithTaskCount]:
        """List projects with task statistics."""
        projects = await self.list(user_id, status, top_level_only=top_level_only)
        result = []

        async with self._session_factory() as session:
            for project in projects:
                # Total tasks
                total = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        TaskORM.project_id == str(project.id)
                    )
                )
                # Completed tasks
                completed = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status == TaskStatus.DONE.value,
                        )
                    )
                )
                # In progress tasks
                in_progress = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status == TaskStatus.IN_PROGRESS.value,
                        )
                    )
                )

                # Unassigned tasks (non-DONE tasks without any assignment)
                unassigned_subquery = (
                    select(TaskAssignmentORM.task_id)
                    .where(TaskAssignmentORM.task_id == TaskORM.id)
                    .correlate(TaskORM)
                    .exists()
                )
                unassigned = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status != TaskStatus.DONE.value,
                            ~unassigned_subquery,
                        )
                    )
                )

                result.append(ProjectWithTaskCount(
                    **project.model_dump(),
                    total_tasks=total.scalar() or 0,
                    completed_tasks=completed.scalar() or 0,
                    in_progress_tasks=in_progress.scalar() or 0,
                    unassigned_tasks=unassigned.scalar() or 0,
                ))

        return result

    async def list_children_with_task_count(
        self,
        user_id: str,
        parent_project_id: UUID,
    ) -> list[ProjectWithTaskCount]:
        """List direct child projects with task statistics.

        Returns ALL children of the parent. The caller is responsible for
        verifying the user has access to the parent project first.
        """
        async with self._session_factory() as session:
            query = (
                select(ProjectORM)
                .where(ProjectORM.parent_project_id == str(parent_project_id))
                .order_by(ProjectORM.created_at.desc())
            )
            result = await session.execute(query)
            projects = [self._orm_to_model(orm) for orm in result.scalars().all()]

        return await self._compute_task_counts(projects)

    async def list_descendants_with_task_count(
        self,
        user_id: str,
        ancestor_project_id: UUID,
    ) -> list[ProjectWithTaskCount]:
        """List all descendant projects (recursive) with task statistics.

        Returns ALL descendants. The caller is responsible for verifying
        the user has access to the ancestor project first.
        """
        async with self._session_factory() as session:
            descendant_cte = text("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM projects WHERE parent_project_id = :ancestor_id
                    UNION ALL
                    SELECT p.id FROM projects p
                    INNER JOIN descendants d ON p.parent_project_id = d.id
                )
                SELECT id FROM descendants
            """)
            desc_result = await session.execute(
                descendant_cte, {"ancestor_id": str(ancestor_project_id)}
            )
            descendant_ids = [row[0] for row in desc_result.fetchall()]

            if not descendant_ids:
                return []

            query = (
                select(ProjectORM)
                .where(ProjectORM.id.in_(descendant_ids))
                .order_by(ProjectORM.created_at.desc())
            )
            result = await session.execute(query)
            projects = [self._orm_to_model(orm) for orm in result.scalars().all()]

        return await self._compute_task_counts(projects)

    async def get_with_task_count(
        self, project_id: UUID
    ) -> Optional[ProjectWithTaskCount]:
        """Get a single project with task statistics (no user check)."""
        project = await self.get_by_id(project_id)
        if not project:
            return None
        results = await self._compute_task_counts([project])
        return results[0] if results else None

    async def _compute_task_counts(
        self, projects: list[Project]
    ) -> list[ProjectWithTaskCount]:
        """Compute task counts for a list of projects."""
        result = []
        async with self._session_factory() as session:
            for project in projects:
                # Total tasks
                total = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        TaskORM.project_id == str(project.id)
                    )
                )
                # Completed tasks
                completed = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status == TaskStatus.DONE.value,
                        )
                    )
                )
                # In progress tasks
                in_progress = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status == TaskStatus.IN_PROGRESS.value,
                        )
                    )
                )

                # Unassigned tasks (non-DONE tasks without any assignment)
                unassigned_subquery = (
                    select(TaskAssignmentORM.task_id)
                    .where(TaskAssignmentORM.task_id == TaskORM.id)
                    .correlate(TaskORM)
                    .exists()
                )
                unassigned = await session.execute(
                    select(func.count(TaskORM.id)).where(
                        and_(
                            TaskORM.project_id == str(project.id),
                            TaskORM.status != TaskStatus.DONE.value,
                            ~unassigned_subquery,
                        )
                    )
                )

                result.append(ProjectWithTaskCount(
                    **project.model_dump(),
                    total_tasks=total.scalar() or 0,
                    completed_tasks=completed.scalar() or 0,
                    in_progress_tasks=in_progress.scalar() or 0,
                    unassigned_tasks=unassigned.scalar() or 0,
                ))

        return result

    async def update(
        self, user_id: str, project_id: UUID, update: ProjectUpdate
    ) -> Project:
        """Update an existing project."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectORM).where(
                    and_(ProjectORM.id == str(project_id), ProjectORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"Project {project_id} not found")

            update_data = update.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if field == "parent_project_id":
                    # Allow setting to None (detach from parent)
                    setattr(orm, field, str(value) if value else None)
                    continue
                if value is not None:
                    if field == "kpi_config" and hasattr(value, "model_dump"):
                        value = value.model_dump()
                    if hasattr(value, "value"):  # Enum
                        value = value.value
                    setattr(orm, field, value)

            orm.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete(self, user_id: str, project_id: UUID) -> bool:
        """Delete a project."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectORM).where(
                    and_(ProjectORM.id == str(project_id), ProjectORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            await session.delete(orm)
            await session.commit()
            return True
