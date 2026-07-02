"""Persistence adapters of the identity module over SQLAlchemy async."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.identity.domain.entities import (
    Permission,
    PermissionEffect,
    Role,
    User,
    UserPermissionOverride,
)
from restaurante.modules.identity.infrastructure.models import (
    PermissionModel,
    PersonModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserPermissionModel,
    UserRoleModel,
)


class SqlAlchemyUserRepository:
    """Implements the `UserRepository` port.

    Always filters explicitly by `tenant_id`; the automatic tenancy filter also
    acts as a safety net.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(
        self, tenant_id: uuid.UUID, email: str
    ) -> User | None:
        stmt = select(UserModel).where(
            UserModel.tenant_id == tenant_id,
            UserModel.email == email,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_id(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> User | None:
        stmt = select(UserModel).where(
            UserModel.tenant_id == tenant_id,
            UserModel.id == user_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create_with_person(
        self,
        tenant_id: uuid.UUID,
        *,
        first_name: str,
        last_name: str,
        email: str,
        hashed_password: str,
        document_number: str | None = None,
        phone: str | None = None,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Create a person and a tenant user linked to it, atomically.

        Returns ``(user_id, person_id)``. Callers MUST check email uniqueness first;
        this commits as a single unit of work (consistent with the other admin writes).
        """
        person = PersonModel(
            first_name=first_name,
            last_name=last_name,
            document_number=document_number,
            phone=phone,
        )
        self._session.add(person)
        await self._session.flush()
        user = UserModel(
            tenant_id=tenant_id,
            person_id=person.id,
            email=email,
            hashed_password=hashed_password,
            name=f"{first_name} {last_name}",
            is_active=True,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user.id, person.id

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            tenant_id=model.tenant_id,
            email=model.email,
            hashed_password=model.hashed_password,
            name=model.name,
            is_active=model.is_active,
            person_id=model.person_id,
            username=model.username,
            last_login_at=model.last_login_at,
        )


def _role_to_domain(model: RoleModel) -> Role:
    return Role(
        id=model.id,
        name=model.name,
        is_global=model.is_global,
        is_active=model.is_active,
        tenant_id=model.tenant_id,
        description=model.description,
    )


class SqlAlchemyRbacRepository:
    """Implements `RbacRepository` (resolution + dynamic management).

    Resolution reads from the DB on every call so granting/revoking a permission
    takes effect on the next request (the JWT carries no permissions). Write
    methods commit their own unit of work since each admin action is atomic.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Resolution --------------------------------------------------------
    async def effective_permission_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str]:
        role_stmt = (
            select(PermissionModel.code)
            .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
            .join(UserRoleModel, UserRoleModel.role_id == RolePermissionModel.role_id)
            .where(
                UserRoleModel.tenant_id == tenant_id,
                UserRoleModel.user_id == user_id,
            )
        )
        override_stmt = (
            select(PermissionModel.code, UserPermissionModel.effect)
            .join(UserPermissionModel, UserPermissionModel.permission_id == PermissionModel.id)
            .where(
                UserPermissionModel.tenant_id == tenant_id,
                UserPermissionModel.user_id == user_id,
            )
        )
        role_codes = set((await self._session.execute(role_stmt)).scalars().all())
        allow: set[str] = set()
        deny: set[str] = set()
        for code, effect in (await self._session.execute(override_stmt)).all():
            (allow if effect == PermissionEffect.ALLOW.value else deny).add(code)
        return frozenset((role_codes | allow) - deny)

    # --- Catalog / roles ---------------------------------------------------
    async def list_permissions(self) -> list[Permission]:
        rows = (
            await self._session.execute(
                select(PermissionModel).order_by(PermissionModel.module, PermissionModel.code)
            )
        ).scalars().all()
        return [
            Permission(
                id=p.id, code=p.code, name=p.name, module=p.module, description=p.description
            )
            for p in rows
        ]

    async def list_roles(self, tenant_id: uuid.UUID) -> list[Role]:
        stmt = select(RoleModel).where(
            or_(RoleModel.tenant_id == tenant_id, RoleModel.is_global.is_(True))
        ).order_by(RoleModel.name)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_role_to_domain(r) for r in rows]

    # --- Users -------------------------------------------------------------
    async def list_tenant_users(self, tenant_id: uuid.UUID) -> list[User]:
        stmt = (
            select(UserModel)
            .where(UserModel.tenant_id == tenant_id)
            .order_by(UserModel.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [SqlAlchemyUserRepository._to_domain(u) for u in rows]

    async def get_role(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID
    ) -> Role | None:
        stmt = select(RoleModel).where(
            RoleModel.id == role_id,
            or_(RoleModel.tenant_id == tenant_id, RoleModel.is_global.is_(True)),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _role_to_domain(model) if model else None

    async def create_role(
        self, tenant_id: uuid.UUID, name: str, description: str | None
    ) -> Role:
        model = RoleModel(
            tenant_id=tenant_id,
            name=name,
            description=description,
            is_global=False,
            is_active=True,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _role_to_domain(model)

    # --- Role <-> permissions ---------------------------------------------
    async def get_role_permission_codes(self, role_id: uuid.UUID) -> set[str]:
        stmt = (
            select(PermissionModel.code)
            .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
            .where(RolePermissionModel.role_id == role_id)
        )
        return set((await self._session.execute(stmt)).scalars().all())

    async def add_role_permission(
        self, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None:
        exists = (
            await self._session.execute(
                select(RolePermissionModel.id).where(
                    RolePermissionModel.role_id == role_id,
                    RolePermissionModel.permission_id == permission_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            self._session.add(
                RolePermissionModel(role_id=role_id, permission_id=permission_id)
            )
            await self._session.commit()

    async def remove_role_permission(
        self, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            delete(RolePermissionModel).where(
                RolePermissionModel.role_id == role_id,
                RolePermissionModel.permission_id == permission_id,
            )
        )
        await self._session.commit()

    async def set_role_permissions(
        self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]
    ) -> None:
        await self._session.execute(
            delete(RolePermissionModel).where(RolePermissionModel.role_id == role_id)
        )
        self._session.add_all(
            RolePermissionModel(role_id=role_id, permission_id=pid)
            for pid in permission_ids
        )
        await self._session.commit()

    # --- User <-> roles ----------------------------------------------------
    async def get_user_roles(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Role]:
        stmt = (
            select(RoleModel)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .where(UserRoleModel.tenant_id == tenant_id, UserRoleModel.user_id == user_id)
            .order_by(RoleModel.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_role_to_domain(r) for r in rows]

    async def get_role_members(
        self, role_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return (tenant_id, user_id) pairs assigned this role (any tenant).

        Used to fan out cache invalidation when a role's permissions change. A
        global role may be assigned across tenants, so we don't filter by tenant.
        """
        rows = (
            await self._session.execute(
                select(UserRoleModel.tenant_id, UserRoleModel.user_id).where(
                    UserRoleModel.role_id == role_id
                )
            )
        ).all()
        return [(tenant_id, user_id) for tenant_id, user_id in rows]

    async def assign_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        exists = (
            await self._session.execute(
                select(UserRoleModel.id).where(
                    UserRoleModel.tenant_id == tenant_id,
                    UserRoleModel.user_id == user_id,
                    UserRoleModel.role_id == role_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            self._session.add(
                UserRoleModel(tenant_id=tenant_id, user_id=user_id, role_id=role_id)
            )
            await self._session.commit()

    async def revoke_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            delete(UserRoleModel).where(
                UserRoleModel.tenant_id == tenant_id,
                UserRoleModel.user_id == user_id,
                UserRoleModel.role_id == role_id,
            )
        )
        await self._session.commit()

    # --- User overrides ----------------------------------------------------
    async def get_user_overrides(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[UserPermissionOverride]:
        stmt = select(UserPermissionModel).where(
            UserPermissionModel.tenant_id == tenant_id,
            UserPermissionModel.user_id == user_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            UserPermissionOverride(
                id=o.id,
                tenant_id=o.tenant_id,
                user_id=o.user_id,
                permission_id=o.permission_id,
                effect=PermissionEffect(o.effect),
            )
            for o in rows
        ]

    async def set_user_override(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        permission_id: uuid.UUID,
        effect: PermissionEffect,
    ) -> None:
        existing = (
            await self._session.execute(
                select(UserPermissionModel).where(
                    UserPermissionModel.tenant_id == tenant_id,
                    UserPermissionModel.user_id == user_id,
                    UserPermissionModel.permission_id == permission_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                UserPermissionModel(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    permission_id=permission_id,
                    effect=effect.value,
                )
            )
        else:
            existing.effect = effect.value
        await self._session.commit()

    async def remove_user_override(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            delete(UserPermissionModel).where(
                UserPermissionModel.tenant_id == tenant_id,
                UserPermissionModel.user_id == user_id,
                UserPermissionModel.permission_id == permission_id,
            )
        )
        await self._session.commit()
