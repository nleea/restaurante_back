"""Create (or top up) an arbitrary tenant with a branch, RBAC and a set of users.

Generalizes ``scripts.seed`` — which hardcodes the ``demo`` tenant — so a second
tenant can be raised for isolation testing without touching the first one.

Usage:
    poetry run python -m scripts.seed_tenant --slug demo2 --name "Demo Dos"
    poetry run python -m scripts.seed_tenant --slug demo2 --password otra1234

Resulting credentials (for --slug demo2, default password ``admin1234``):
    Host: demo2.<BASE_DOMAIN>
    admin@demo2.com    -> admin    (todos los permisos)
    gerente@demo2.com  -> manager
    cajero@demo2.com   -> cashier
    mesero@demo2.com   -> waiter

Idempotent: every row is looked up by its natural key before insert, so running
it twice only fills in what is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Registra todos los modelos en Base.metadata (FKs cruzadas, p.ej. tenants->cities).
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.identity.infrastructure.models import (
    RoleModel,
    UserModel,
    UserRoleModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.security.password import Argon2PasswordHasher
from restaurante.shared.tenancy.branch_code import validate_branch_code
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from scripts.seed import seed_rbac

DEFAULT_BRANCH_CODE = "main"
DEFAULT_PASSWORD = "admin1234"

# local-part -> (display name, base role name)
USER_TEMPLATE: dict[str, tuple[str, str]] = {
    "admin": ("Administrador", "admin"),
    "gerente": ("Gerente", "manager"),
    "cajero": ("Cajero", "cashier"),
    "mesero": ("Mesero", "waiter"),
}

# El slug viaja como subdominio: solo minúsculas, dígitos y guiones.
SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def validate_slug(value: str) -> str:
    if not SLUG_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"invalid tenant slug {value!r}: use lowercase letters, digits and hyphens"
        )
    return value


async def ensure_tenant(session: AsyncSession, slug: str, name: str) -> TenantModel:
    tenant = (
        await session.execute(select(TenantModel).where(TenantModel.slug == slug))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = TenantModel(slug=slug, name=name, is_active=True)
        session.add(tenant)
        await session.flush()
        print(f"Tenant created: {tenant.slug} ({tenant.id})")
    else:
        print(f"Tenant already exists: {tenant.slug} ({tenant.id})")
    return tenant


async def ensure_branch(
    session: AsyncSession, tenant: TenantModel, code: str
) -> BranchModel:
    branch = (
        await session.execute(
            select(BranchModel).where(
                BranchModel.tenant_id == tenant.id, BranchModel.code == code
            )
        )
    ).scalar_one_or_none()
    if branch is None:
        branch = BranchModel(
            tenant_id=tenant.id,
            code=validate_branch_code(code),
            name="Main Branch",
            is_active=True,
        )
        session.add(branch)
        await session.flush()
        print(f"Branch created: {code}")
    else:
        print(f"Branch already exists: {code}")
    return branch


async def ensure_user(
    session: AsyncSession,
    tenant: TenantModel,
    email: str,
    name: str,
    role: RoleModel,
    hashed_password: str,
) -> None:
    user = (
        await session.execute(
            select(UserModel).where(
                UserModel.tenant_id == tenant.id, UserModel.email == email
            )
        )
    ).scalar_one_or_none()
    if user is None:
        user = UserModel(
            tenant_id=tenant.id,
            email=email,
            hashed_password=hashed_password,
            name=name,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        print(f"User created: {email} ({role.name})")
    else:
        print(f"User already exists: {email}")

    assigned = (
        await session.execute(
            select(UserRoleModel).where(
                UserRoleModel.tenant_id == tenant.id,
                UserRoleModel.user_id == user.id,
                UserRoleModel.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if assigned is None:
        session.add(
            UserRoleModel(tenant_id=tenant.id, user_id=user.id, role_id=role.id)
        )
        print(f"  assigned role '{role.name}' to {email}")


async def seed_tenant(
    slug: str, name: str, branch_code: str, password: str, email_domain: str
) -> None:
    hasher = Argon2PasswordHasher()
    hashed_password = hasher.hash(password)

    async with SessionFactory() as session:
        tenant = await ensure_tenant(session, slug, name)
        await ensure_branch(session, tenant, branch_code)

        # Los roles base son globales (tenant_id NULL): se comparten entre tenants.
        roles = await seed_rbac(session)
        print(f"RBAC ready: {len(roles)} base roles")

        for local_part, (display_name, role_name) in USER_TEMPLATE.items():
            await ensure_user(
                session,
                tenant,
                email=f"{local_part}@{email_domain}",
                name=f"{display_name} {name}",
                role=roles[role_name],
                hashed_password=hashed_password,
            )

        await session.commit()

    print(f"\nDone. Log in at https://{slug}.<BASE_DOMAIN> with password: {password}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, type=validate_slug)
    parser.add_argument("--name", default=None, help="Display name (default: slug)")
    parser.add_argument("--branch-code", default=DEFAULT_BRANCH_CODE)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--email-domain",
        default=None,
        help="Domain for the seeded user emails (default: <slug>.com)",
    )
    args = parser.parse_args()

    asyncio.run(
        seed_tenant(
            slug=args.slug,
            name=args.name or args.slug,
            branch_code=args.branch_code,
            password=args.password,
            email_domain=args.email_domain or f"{args.slug}.com",
        )
    )


if __name__ == "__main__":
    main()
