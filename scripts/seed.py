"""Minimal development seed: demo tenant, branch, admin user and RBAC baseline.

Usage:
    poetry run python -m scripts.seed

Resulting credentials:
    subdomain: demo   (Host: demo.<BASE_DOMAIN>)
    email:     admin@demo.com
    password:  admin1234   (assigned the global `admin` role -> all permissions)
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select
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
from restaurante.shared.tenancy.branch_code import validate_branch_code
from restaurante.shared.tenancy.models import BranchModel, TenantModel

DEMO_SLUG = "demo"
# Slug-form: the code addresses the branch in the public carta URL (/store/<code>).
DEMO_BRANCH_CODE = "main"
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


def admin_email_for(slug: str) -> str:
    """`demo` → `admin@demo.com`. El correo es único POR TENANT (uq_users_tenant_email),
    así que derivarlo del slug no colisiona; sólo evita que dos negocios compartan
    literalmente la misma casilla."""
    return f"admin@{slug}.com"


async def seed(
    slug: str = DEMO_SLUG,
    tenant_name: str = "Demo Restaurant",
    branch_code: str = DEMO_BRANCH_CODE,
    email: str | None = None,
    password: str = DEMO_PASSWORD,
) -> None:
    email = email or admin_email_for(slug)
    hasher = Argon2PasswordHasher()
    async with SessionFactory() as session:
        tenant = (
            await session.execute(
                select(TenantModel).where(TenantModel.slug == slug)
            )
        ).scalar_one_or_none()
        if tenant is None:
            tenant = TenantModel(slug=slug, name=tenant_name, is_active=True)
            session.add(tenant)
            await session.flush()
            print(f"Tenant created: {tenant.slug} ({tenant.id})")
        else:
            print(f"Tenant already exists: {tenant.slug} ({tenant.id})")

        # Sin mayúsculas: el código de la sede se edita desde el panel, y un negocio que
        # renombró la suya a "MAIN" no puede acabar con DOS sedes principales cada vez que
        # alguien vuelve a sembrar. Se busca la que ya existe antes de crear otra.
        branch = (
            await session.execute(
                select(BranchModel).where(
                    BranchModel.tenant_id == tenant.id,
                    func.lower(BranchModel.code) == branch_code.lower(),
                )
            )
        ).scalars().first()
        if branch is None:
            session.add(
                BranchModel(
                    tenant_id=tenant.id,
                    code=validate_branch_code(branch_code),
                    name="Main Branch",
                    is_active=True,
                )
            )
            print(f"Branch created: {branch_code}")
        else:
            print(f"Branch already exists: {branch_code}")

        roles = await seed_rbac(session)
        print(f"RBAC seeded: {len(PERMISSIONS)} permissions, {len(roles)} base roles")

        user = (
            await session.execute(
                select(UserModel).where(
                    UserModel.tenant_id == tenant.id,
                    UserModel.email == email,
                )
            )
        ).scalar_one_or_none()
        if user is None:
            user = UserModel(
                tenant_id=tenant.id,
                email=email,
                hashed_password=hasher.hash(password),
                name=f"{tenant_name} Administrator",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"User created: {email} / {password}")
        else:
            print(f"User already exists: {email}")

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
            print(f"Assigned '{ADMIN_ROLE_NAME}' role to {email}")

        await session.commit()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default=DEMO_SLUG, help="subdominio del tenant")
    parser.add_argument("--name", default=None, help="nombre visible del negocio")
    parser.add_argument("--branch", default=DEMO_BRANCH_CODE, help="código de la sede")
    parser.add_argument(
        "--email", default=None, help="correo del admin (por defecto admin@<slug>.com)"
    )
    parser.add_argument("--password", default=DEMO_PASSWORD)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        seed(
            slug=args.slug,
            tenant_name=args.name or f"{args.slug.title()} Restaurant",
            branch_code=args.branch,
            email=args.email,
            password=args.password,
        )
    )
