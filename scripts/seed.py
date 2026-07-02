"""Minimal development seed: demo tenant, branch, admin user and RBAC baseline.

Usage:
    poetry run python -m scripts.seed

Resulting credentials:
    subdomain: demo   (Host: demo.<BASE_DOMAIN>)
    email:     admin@demo.com
    password:  admin1234   (assigned the global `admin` role -> all permissions)
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Registra todos los modelos en Base.metadata (FKs cruzadas, p.ej. tenants->cities).
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.identity.domain.permissions_catalog import (
    ADMIN_ROLE_NAME,
    BASE_ROLES,
    PERMISSIONS,
)
from restaurante.modules.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserRoleModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.security.password import Argon2PasswordHasher
from restaurante.shared.tenancy.models import BranchModel, TenantModel

DEMO_SLUG = "demo"
DEMO_BRANCH_CODE = "MAIN"
DEMO_EMAIL = "admin@demo.com"
DEMO_PASSWORD = "admin1234"


async def seed_rbac(session: AsyncSession) -> dict[str, RoleModel]:
    """Idempotently upsert the permission catalog and base global roles.

    Returns a map of base role name -> RoleModel (already flushed, with ids).
    """
    # Permissions
    existing_perms = {
        p.code: p
        for p in (await session.execute(select(PermissionModel))).scalars().all()
    }
    for definition in PERMISSIONS:
        if definition.code not in existing_perms:
            model = PermissionModel(
                code=definition.code,
                name=definition.name,
                module=definition.module,
                description=definition.description,
            )
            session.add(model)
            existing_perms[definition.code] = model
    await session.flush()

    # Base global roles + their permissions (additive)
    roles: dict[str, RoleModel] = {}
    for role_name, codes in BASE_ROLES.items():
        role = (
            await session.execute(
                select(RoleModel).where(
                    RoleModel.name == role_name, RoleModel.is_global.is_(True)
                )
            )
        ).scalar_one_or_none()
        if role is None:
            role = RoleModel(
                tenant_id=None,
                name=role_name,
                description=f"Base role: {role_name}",
                is_global=True,
                is_active=True,
            )
            session.add(role)
            await session.flush()
        roles[role_name] = role

        current = {
            c
            for c in (
                await session.execute(
                    select(PermissionModel.code)
                    .join(
                        RolePermissionModel,
                        RolePermissionModel.permission_id == PermissionModel.id,
                    )
                    .where(RolePermissionModel.role_id == role.id)
                )
            ).scalars().all()
        }
        for code in codes - current:
            session.add(
                RolePermissionModel(
                    role_id=role.id, permission_id=existing_perms[code].id
                )
            )
    await session.flush()
    return roles


async def seed() -> None:
    hasher = Argon2PasswordHasher()
    async with SessionFactory() as session:
        tenant = (
            await session.execute(
                select(TenantModel).where(TenantModel.slug == DEMO_SLUG)
            )
        ).scalar_one_or_none()
        if tenant is None:
            tenant = TenantModel(slug=DEMO_SLUG, name="Demo Restaurant", is_active=True)
            session.add(tenant)
            await session.flush()
            print(f"Tenant created: {tenant.slug} ({tenant.id})")
        else:
            print(f"Tenant already exists: {tenant.slug} ({tenant.id})")

        branch = (
            await session.execute(
                select(BranchModel).where(
                    BranchModel.tenant_id == tenant.id,
                    BranchModel.code == DEMO_BRANCH_CODE,
                )
            )
        ).scalar_one_or_none()
        if branch is None:
            session.add(
                BranchModel(
                    tenant_id=tenant.id,
                    code=DEMO_BRANCH_CODE,
                    name="Main Branch",
                    is_active=True,
                )
            )
            print(f"Branch created: {DEMO_BRANCH_CODE}")
        else:
            print(f"Branch already exists: {DEMO_BRANCH_CODE}")

        roles = await seed_rbac(session)
        print(f"RBAC seeded: {len(PERMISSIONS)} permissions, {len(roles)} base roles")

        user = (
            await session.execute(
                select(UserModel).where(
                    UserModel.tenant_id == tenant.id,
                    UserModel.email == DEMO_EMAIL,
                )
            )
        ).scalar_one_or_none()
        if user is None:
            user = UserModel(
                tenant_id=tenant.id,
                email=DEMO_EMAIL,
                hashed_password=hasher.hash(DEMO_PASSWORD),
                name="Demo Administrator",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"User created: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"User already exists: {DEMO_EMAIL}")

        admin_role = roles[ADMIN_ROLE_NAME]
        already_admin = (
            await session.execute(
                select(UserRoleModel).where(
                    UserRoleModel.tenant_id == tenant.id,
                    UserRoleModel.user_id == user.id,
                    UserRoleModel.role_id == admin_role.id,
                )
            )
        ).scalar_one_or_none()
        if already_admin is None:
            session.add(
                UserRoleModel(
                    tenant_id=tenant.id, user_id=user.id, role_id=admin_role.id
                )
            )
            print(f"Assigned '{ADMIN_ROLE_NAME}' role to {DEMO_EMAIL}")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
