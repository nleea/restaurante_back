# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. Plan Node Default 
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions) 
- If something goes sideways, STOP and re-plan immediately 
- don't keep pushing - Use plan mode for verification steps, not just building 
- Write detailed specs upfront to reduce ambiguity 
--- 
### 2. Subagent Strategy 
- Use subagents liberally to keep main context window clean 
- Offload research, exploration, and parallel analysis to subagents 
- For complex problems, throw more compute at it via subagents 
- One task per subagent for focused execution 
--- 
### 3. Self-Improvement Loop 
- After ANY correction from the user: update `tasks/lessons.md` with the pattern 
- Write rules for yourself that prevent the same mistake 
- Ruthlessly iterate on these lessons until mistake rate drops 
- Review lessons at session start for relevant project 
--- 
### 4. Verification Before Done 
- Never mark a task complete without proving it works 
- Diff behavior between main and your changes when relevant 
- Ask yourself: "Would a staff engineer approve this?" 
- Run tests, check logs, demonstrate correctness 
--- 
### 5. Demand Elegance (Balanced) 
- For non-trivial changes: pause and ask "is there a more elegant way?" 
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution" 
- Skip this for simple, obvious fixes 
- don't over-engineer 
- Challenge your own work before presenting it 
--- 
### 6. Autonomous Bug Fixing 
- When given a bug report: just fix it. Don't ask for hand-holding 
- Point at logs, errors, failing tests 
- then resolve them 
- Zero context switching required from the user 
- Go fix failing CI tests without being told how 
--- 
## Task Management 
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items 
2. **Verify Plan**: Check in before starting implementation 
3. **Track Progress**: Mark items complete as you go 
4. **Explain Changes**: High-level summary at each step 
5. **Document Results**: Add review section to `tasks/todo.md` 
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections 
---
 ## Core Principles 
- **Simplicity First**: Make every change as simple as possible. Impact minimal code 
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards

## Stack & Commands

Backend: **FastAPI + SQLAlchemy 2.0 async (asyncpg) + PostgreSQL + Alembic**, Poetry.
Architecture: **hexagonal** (ports & adapters), modular by domain under `src/restaurante/`.
Tenancy: **row-level `tenant_id`**, tenant resolved by **subdomain** (`<slug>.<BASE_DOMAIN>`).
Auth: JWT **access + refresh**, Argon2 password hashing.

```bash
poetry install
docker compose up -d db                 # Postgres local
poetry run alembic upgrade head         # apply migrations
poetry run python -m scripts.seed       # demo tenant + admin@demo.com / admin1234
poetry run python -m scripts.seed_demo  # rich demo dataset for live testing (insumos, rutas, orders...) — idempotent
poetry run uvicorn restaurante.main:app --reload
poetry run pytest                       # tests (sqlite, no Postgres needed)
poetry run pytest path::test_name       # single test
poetry run ruff check .                 # lint
poetry run mypy src                     # types (strict)
poetry run alembic revision --autogenerate -m "msg"   # new migration
```

Layering rule: `API → application → domain`; `infrastructure` implements domain ports.
Domain stays framework-free. New business modules go under `src/restaurante/modules/<name>/`
following identity's structure. Their ORM models must use `BranchScopedMixin`
(`shared/database.py`) — which adds both `tenant_id` and `branch_id` and triggers the
automatic tenant filter (`shared/tenancy/filtering.py`); use `TenantScopedMixin` only for
tenant-level (non-branch) entities. Register new model modules in `migrations/env.py` so
autogenerate sees them.

## Product

The product is a **multi-tenant SaaS for restaurant management** (not a generic business tool), positioned closer to back-office strength (purchasing, costing, finance) than pure POS. Market references: Toast, Square, Loyverse.

**Naming rule (binding): all code and database identifiers are in English.** Tables, columns, constraints, indexes, ORM models, domain entities, value objects, use cases, ports, adapters, functions, variables and test names use English (e.g. `branches`/`BranchModel`, `users`/`UserModel`, `branch_id`, `code`, `name`, `is_active`). The Spanish-only domain vocabulary from the docs (e.g. *comanda*, *sucursal*, *arqueo*, *receta*) stays in **prose** — documentation, product references and market positioning — and must be mapped to an English identifier in code (*comanda*→`order`/`ticket`, *sucursal*→`branch`, *receta*→`recipe`, *arqueo*→`cash count`). Pick the English mapping once per concept and keep it consistent.

## Binding architectural decisions

These are the load-bearing decisions from `docs/Primer Alcance.md` that constrain almost every future design choice. Follow them unless the user explicitly revises them.

- **Multi-tenant with full data isolation.** Every business (tenant) is fully isolated. The scope references prior experience with DB-per-tenant + subdomain + JWT (from a project called "Sellaris"); the tenancy strategy (DB-per-tenant vs. row-level `tenant_id`) is an open decision to confirm before modeling tables.
- **Multi-branch by data model, single-branch in practice.** Restaurants run one branch today, but the system must be designed for N branches from day one. **Every business-relevant entity must carry a `branch_id` (branch id) from the start** — inventory, cash register, staff, orders, etc. This avoids a painful migration later. The consolidated multi-branch *reporting* features are Phase 2, but the column is not optional.
- **Design gate (do not skip):** a module enters scope only when it has a clear answer to *what business problem it solves* and *which module it connects to*. Prefer a small complete system over a large half-built one.

## Module map and how it fits together

The system is organized as layers feeding each other (see `docs/Primer Alcance.md` §3 for the full tree). The non-obvious connections that require reading multiple modules to understand:

- **Recetas / Costeo (BOM) is the critical hinge.** It defines what inputs make up each sellable product (e.g. 1 burger = 150g meat + 1 bun). It is the *only* link between "what I sell" (Pedidos/Productos) and "what I have in stock" (Inventario). Without it, selling a dish never decrements real inventory and product-level margin/profitability cannot be computed. Treat it as foundational, not a nice-to-have.
- **Pedidos (Comandas) is the operational core.** It connects Mesas, Productos, Cocina (KDS), Delivery, Caja, and triggers inventory deduction *via Recetas*.
- **Delivery uses an own fleet, not external apps** (no Rappi-style integrations). This means it needs real driver management (drivers are employees under Personal y Turnos), manual/auto assignment, and explicit states (pendiente → asignado → en camino → entregado/no entregado) — not just a status field. Cash-on-delivery is common, so it touches Caja.
- **Notificaciones and Auditoría/Logs are cross-cutting**, not business modules. They are cheap to include if planned into the data model from the start and expensive to retrofit — design entities with them in mind.

## Context

- Target market is Colombia — expect payment methods like Nequi/Daviplata and eventual DIAN fiscal requirements when a business grows.
- The driving constraint is that **3 real pilot restaurants** must be able to run daily operations without falling back to Excel or paper. Use that as the bar for what "indispensable" means.
