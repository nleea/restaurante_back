"""Persistence adapter for the messaging module.

Owns the four `whatsapp_*` tables. Reads `branches` (a session's anchor) and
`employees`/`users` (to name whoever holds a conversation) — never writes them.

Two methods carry the module's load-bearing guarantees and are worth reading
closely: `add_inbound_message_once` (idempotency against the bridge's redeliveries)
and `claim_conversation` (atomic claiming without a lock table).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.menu.infrastructure.models import (
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.messaging.domain.delivery import advance
from restaurante.modules.messaging.domain.entities import (
    AutoreplySettings,
    FaqEntry,
    QuickReply,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppSession,
)
from restaurante.modules.messaging.domain.ports import (
    BusinessIdentity,
    ConversationSummary,
    OrderContext,
    OrderLineSummary,
    UnsettledOrder,
)
from restaurante.modules.messaging.infrastructure.models import (
    OPEN_CONVERSATION_STATUSES,
    WhatsAppAutoreplySettingsModel,
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
    WhatsAppOutboundEmissionModel,
    WhatsAppSessionModel,
    emission_key,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderPaymentClaimModel,
    OrderPaymentModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.phones import normalize_phone
from restaurante.shared.tenancy.models import BranchModel, TenantModel

_PREVIEW_CHARS = 120


def _session(m: WhatsAppSessionModel) -> WhatsAppSession:
    return WhatsAppSession(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        provider_instance_ref=m.provider_instance_ref,
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
        phone_number=m.phone_number,
        last_seen_at=m.last_seen_at,
    )


def _contact(m: WhatsAppContactModel) -> WhatsAppContact:
    return WhatsAppContact(
        id=m.id,
        tenant_id=m.tenant_id,
        phone=m.phone,
        created_at=m.created_at,
        updated_at=m.updated_at,
        name=m.name,
        address=m.address,
    )


def _settings(m: WhatsAppAutoreplySettingsModel) -> AutoreplySettings:
    return AutoreplySettings(
        id=m.id,
        tenant_id=m.tenant_id,
        greeting_enabled=m.greeting_enabled,
        greeting_open_text=m.greeting_open_text,
        greeting_closed_text=m.greeting_closed_text,
        greeting_awaiting_payment_text=m.greeting_awaiting_payment_text,
        assistant_offer_enabled=m.assistant_offer_enabled,
        idle_hours=m.idle_hours,
        token_lifetime_hours=m.token_lifetime_hours,
        status_mapping=dict(m.status_mapping or {}),
        # `None` se conserva como `None`: es "nunca las tocó", y colapsarlo a `[]` aquí sería
        # perder la única diferencia que impide que una FAQ borrada resucite.
        faqs=None if m.faqs is None else [_faq_entry(raw) for raw in m.faqs],
        # Mismo trato del `None`, misma razón. Aquí el que resucitaría es una plantilla borrada.
        quick_replies=(
            None
            if m.quick_replies is None
            else [_quick_reply(raw) for raw in m.quick_replies]
        ),
    )


def _faq_entry(raw: Any) -> FaqEntry:
    """Una fila del JSON a entidad, tolerante con lo que falte.

    Tolerante porque el JSON lo escribió una versión anterior del cliente: una FAQ sin `enabled`
    se lee apagada, y una sin gatillos no coincide con nada. Ninguno de los dos casos puede
    tumbar la lectura de los ajustes enteros.
    """
    data = raw if isinstance(raw, dict) else {}
    return FaqEntry(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        triggers=[str(t) for t in (data.get("triggers") or []) if str(t).strip()],
        text=str(data.get("text") or ""),
        enabled=bool(data.get("enabled", False)),
    )


def _faq_json(faq: FaqEntry) -> dict[str, Any]:
    return {
        "id": faq.id,
        "name": faq.name,
        "triggers": list(faq.triggers),
        "text": faq.text,
        "enabled": faq.enabled,
    }


def _quick_reply(raw: Any) -> QuickReply:
    """Una fila del JSON a entidad, tolerante con lo que falte, como `_faq_entry`.

    Una plantilla sin texto se lee vacía y la pantalla la enseña vacía para que la arreglen; lo
    que no puede es tumbar la lectura de los ajustes enteros.
    """
    data = raw if isinstance(raw, dict) else {}
    return QuickReply(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        text=str(data.get("text") or ""),
    )


def _quick_reply_json(entry: QuickReply) -> dict[str, Any]:
    return {"id": entry.id, "name": entry.name, "text": entry.text}


def _conversation(m: WhatsAppConversationModel) -> WhatsAppConversation:
    return WhatsAppConversation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        whatsapp_contact_id=m.whatsapp_contact_id,
        status=m.status,
        started_at=m.started_at,
        employee_id=m.employee_id,
        closed_at=m.closed_at,
        store_token=m.store_token,
        store_token_expires_at=m.store_token_expires_at,
    )


def _message(m: WhatsAppMessageModel) -> WhatsAppMessage:
    return WhatsAppMessage(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        whatsapp_conversation_id=m.whatsapp_conversation_id,
        sender_type=m.sender_type,
        content=m.content,
        delivery_state=m.delivery_state,
        sent_at=m.sent_at,
        employee_id=m.employee_id,
        provider_message_id=m.provider_message_id,
        media_type=m.media_type,
        media_mime=m.media_mime,
        media_url=m.media_url,
    )


class SqlAlchemyMessagingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Sessions ------------------------------------------------------------
    async def get_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> WhatsAppSession | None:
        stmt = select(WhatsAppSessionModel).where(
            WhatsAppSessionModel.id == session_id,
            WhatsAppSessionModel.tenant_id == tenant_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _session(row) if row else None

    async def get_session_for_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> WhatsAppSession | None:
        stmt = select(WhatsAppSessionModel).where(
            WhatsAppSessionModel.tenant_id == tenant_id,
            WhatsAppSessionModel.branch_id == branch_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _session(row) if row else None

    async def find_session_by_instance_ref(
        self, provider_instance_ref: str
    ) -> WhatsAppSession | None:
        # No tenant filter: the webhook has no subdomain to resolve one from, so the
        # instance reference IS the tenant proof. It is unique per tenant and the
        # bridge generates it, so it is not guessable.
        stmt = select(WhatsAppSessionModel).where(
            WhatsAppSessionModel.provider_instance_ref == provider_instance_ref
        )
        row = (
            await self._session.execute(stmt.execution_options(skip_tenant_filter=True))
        ).scalar_one_or_none()
        return _session(row) if row else None

    async def list_sessions(self, tenant_id: uuid.UUID) -> list[WhatsAppSession]:
        stmt = (
            select(WhatsAppSessionModel)
            .where(WhatsAppSessionModel.tenant_id == tenant_id)
            .order_by(WhatsAppSessionModel.created_at)
        )
        return [_session(m) for m in (await self._session.execute(stmt)).scalars()]

    async def create_session(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        provider_instance_ref: str,
    ) -> WhatsAppSession:
        model = WhatsAppSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            provider_instance_ref=provider_instance_ref,
            status="disconnected",
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _session(model)

    async def update_session(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        changes: dict[str, Any],
    ) -> WhatsAppSession | None:
        if not changes:
            return await self.get_session(tenant_id, session_id)
        stmt = (
            sql_update(WhatsAppSessionModel)
            .where(
                WhatsAppSessionModel.id == session_id,
                WhatsAppSessionModel.tenant_id == tenant_id,
            )
            .values(**changes)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return await self.get_session(tenant_id, session_id)

    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Contacts ------------------------------------------------------------
    async def find_contact_by_phone(
        self, tenant_id: uuid.UUID, phone: str
    ) -> WhatsAppContact | None:
        stmt = select(WhatsAppContactModel).where(
            WhatsAppContactModel.tenant_id == tenant_id,
            WhatsAppContactModel.phone == normalize_phone(phone),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _contact(row) if row else None

    async def get_contact(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppContact | None:
        stmt = select(WhatsAppContactModel).where(
            WhatsAppContactModel.id == contact_id,
            WhatsAppContactModel.tenant_id == tenant_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _contact(row) if row else None

    async def find_or_create_contact(
        self, tenant_id: uuid.UUID, phone: str, name: str | None = None
    ) -> WhatsAppContact:
        # Se guarda en forma canónica. Lo que llega del JID ya lo es, así que esto no cambia
        # nada para el camino normal — pero impide que otro camino cree un contacto con
        # espacios que luego ninguna búsqueda encuentre.
        phone = normalize_phone(phone)
        existing = await self.find_contact_by_phone(tenant_id, phone)
        if existing:
            # The bridge learns the pushname over time; fill it in, never overwrite.
            if name and not existing.name:
                await self._session.execute(
                    sql_update(WhatsAppContactModel)
                    .where(WhatsAppContactModel.id == existing.id)
                    .values(name=name)
                )
                await self._session.commit()
                existing.name = name
            return existing

        model = WhatsAppContactModel(tenant_id=tenant_id, phone=phone, name=name)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _contact(model)

    async def list_contactable(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, str]]:
        """Los chats a los que SE PUEDE escribir en esta sucursal: `(id, nombre, dirección)`.

        "Se puede escribir" = escribieron ellos primero. Es la misma condición que exige el
        guardián, así que esta lista es exactamente el conjunto de destinos válidos — y por
        eso sirve para emparejar a un empleado con su chat sin adivinar nada.

        La "dirección" es el `phone` del contacto, que puede ser un número o un `@lid`. A
        efectos de enviar da igual: es lo que el puente necesita.
        """
        stmt = (
            select(
                WhatsAppContactModel.id,
                WhatsAppContactModel.name,
                WhatsAppContactModel.phone,
            )
            .join(
                WhatsAppConversationModel,
                WhatsAppConversationModel.whatsapp_contact_id
                == WhatsAppContactModel.id,
            )
            .join(
                WhatsAppMessageModel,
                WhatsAppMessageModel.whatsapp_conversation_id
                == WhatsAppConversationModel.id,
            )
            .where(
                WhatsAppContactModel.tenant_id == tenant_id,
                WhatsAppConversationModel.branch_id == branch_id,
                WhatsAppMessageModel.sender_type == "contact",
            )
            .group_by(
                WhatsAppContactModel.id,
                WhatsAppContactModel.name,
                WhatsAppContactModel.phone,
            )
            .order_by(func.max(WhatsAppMessageModel.sent_at).desc())
        )
        return [(r[0], r[1], r[2]) for r in (await self._session.execute(stmt)).all()]

    async def is_reachable(self, tenant_id: uuid.UUID, phone: str) -> bool:
        """A contact exists for the phone AND has written at least once.

        One query, no branch scope: writing to any branch of the business makes the
        person reachable by the business.

        El teléfono se normaliza antes de comparar. Los contactos se guardan tal y como
        salen del JID (dígitos pelados), pero quien pregunta puede traer un número que
        tecleó una persona —`+57 300 111 2233`—, y comparar eso literalmente devuelve "no
        contactable" sin ningún error: el aviso simplemente no sale.
        """
        phone = normalize_phone(phone)
        stmt = (
            select(WhatsAppMessageModel.id)
            .join(
                WhatsAppConversationModel,
                WhatsAppConversationModel.id
                == WhatsAppMessageModel.whatsapp_conversation_id,
            )
            .join(
                WhatsAppContactModel,
                WhatsAppContactModel.id
                == WhatsAppConversationModel.whatsapp_contact_id,
            )
            .where(
                WhatsAppContactModel.tenant_id == tenant_id,
                WhatsAppContactModel.phone == phone,
                WhatsAppMessageModel.sender_type == "contact",
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Conversations -------------------------------------------------------
    async def get_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        stmt = select(WhatsAppConversationModel).where(
            WhatsAppConversationModel.id == conversation_id,
            WhatsAppConversationModel.tenant_id == tenant_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _conversation(row) if row else None

    async def find_open_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        """The contact's most recently active open thread on this branch.

        Answers a fact, not a policy: whether that thread is too old to join is the
        idle window, which belongs to the service.
        """
        last_message_at = (
            select(func.max(WhatsAppMessageModel.sent_at))
            .where(
                WhatsAppMessageModel.whatsapp_conversation_id
                == WhatsAppConversationModel.id
            )
            .correlate(WhatsAppConversationModel)
            .scalar_subquery()
        )
        stmt = (
            select(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.tenant_id == tenant_id,
                WhatsAppConversationModel.branch_id == branch_id,
                WhatsAppConversationModel.whatsapp_contact_id == contact_id,
                WhatsAppConversationModel.status.in_(OPEN_CONVERSATION_STATUSES),
            )
            .order_by(
                func.coalesce(
                    last_message_at, WhatsAppConversationModel.started_at
                ).desc()
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _conversation(row) if row else None

    async def find_latest_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        """The contact's most recent thread on this branch, OPEN OR CLOSED.

        Same query as `find_open_conversation` minus the status filter. It exists for the one
        message that must reach a customer whose thread we already closed: the payment link
        for an order they have just placed. Closing is our own bookkeeping — it happens on
        `delivered`, so a repeat customer is closed by definition — and it is not what protects
        the number. That is `is_reachable` in the gateway, which still applies.
        """
        last_message_at = (
            select(func.max(WhatsAppMessageModel.sent_at))
            .where(
                WhatsAppMessageModel.whatsapp_conversation_id
                == WhatsAppConversationModel.id
            )
            .correlate(WhatsAppConversationModel)
            .scalar_subquery()
        )
        stmt = (
            select(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.tenant_id == tenant_id,
                WhatsAppConversationModel.branch_id == branch_id,
                WhatsAppConversationModel.whatsapp_contact_id == contact_id,
            )
            .order_by(
                func.coalesce(
                    last_message_at, WhatsAppConversationModel.started_at
                ).desc()
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _conversation(row) if row else None

    async def last_activity_at(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> datetime | None:
        """When the thread last moved: its newest message, else when it started."""
        stmt = select(
            func.max(WhatsAppMessageModel.sent_at),
        ).where(WhatsAppMessageModel.whatsapp_conversation_id == conversation_id)
        latest = (await self._session.execute(stmt)).scalar_one_or_none()
        if latest is None:
            started = (
                await self._session.execute(
                    select(WhatsAppConversationModel.started_at).where(
                        WhatsAppConversationModel.id == conversation_id,
                        WhatsAppConversationModel.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
            latest = started
        if latest is None:
            return None
        # SQLite hands back naive datetimes; normalise or the subtraction explodes.
        return latest if latest.tzinfo else latest.replace(tzinfo=UTC)

    async def create_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation:
        model = WhatsAppConversationModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            whatsapp_contact_id=contact_id,
            status="new",
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _conversation(model)

    async def list_conversations(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        include_closed: bool = False,
    ) -> list[ConversationSummary]:
        """Inbox list: conversation + contact + last-message preview, newest first.

        The preview is derived from the messages table rather than denormalised onto
        the conversation, so there is exactly one place where "what was said last"
        lives. Correlated subqueries keep it portable across Postgres and SQLite.
        """
        last_at = (
            select(func.max(WhatsAppMessageModel.sent_at))
            .where(
                WhatsAppMessageModel.whatsapp_conversation_id
                == WhatsAppConversationModel.id
            )
            .correlate(WhatsAppConversationModel)
            .scalar_subquery()
        )
        counted = (
            select(func.count(WhatsAppMessageModel.id))
            .where(
                WhatsAppMessageModel.whatsapp_conversation_id
                == WhatsAppConversationModel.id
            )
            .correlate(WhatsAppConversationModel)
            .scalar_subquery()
        )
        stmt = (
            select(WhatsAppConversationModel, WhatsAppContactModel, last_at, counted)
            .join(
                WhatsAppContactModel,
                WhatsAppContactModel.id
                == WhatsAppConversationModel.whatsapp_contact_id,
            )
            .where(
                WhatsAppConversationModel.tenant_id == tenant_id,
                WhatsAppConversationModel.branch_id == branch_id,
            )
            .order_by(
                func.coalesce(last_at, WhatsAppConversationModel.started_at).desc()
            )
        )
        if not include_closed:
            stmt = stmt.where(
                WhatsAppConversationModel.status.in_(OPEN_CONVERSATION_STATUSES)
            )

        rows = (await self._session.execute(stmt)).all()
        summaries: list[ConversationSummary] = []
        holder_names: dict[uuid.UUID, str | None] = {}
        for conversation, contact, last_message_at, message_count in rows:
            preview, sender_type = await self._last_message_preview(conversation.id)
            holder: str | None = None
            if conversation.employee_id is not None:
                if conversation.employee_id not in holder_names:
                    holder_names[conversation.employee_id] = (
                        await self.employee_display_name(
                            tenant_id, conversation.employee_id
                        )
                    )
                holder = holder_names[conversation.employee_id]
            summaries.append(
                ConversationSummary(
                    conversation=_conversation(conversation),
                    contact=_contact(contact),
                    last_message_at=last_message_at,
                    last_message_preview=preview,
                    last_message_sender_type=sender_type,
                    message_count=int(message_count or 0),
                    holder_name=holder,
                )
            )
        return summaries

    async def _last_message_preview(
        self, conversation_id: uuid.UUID
    ) -> tuple[str | None, str | None]:
        stmt = (
            select(WhatsAppMessageModel.content, WhatsAppMessageModel.sender_type)
            .where(WhatsAppMessageModel.whatsapp_conversation_id == conversation_id)
            .order_by(WhatsAppMessageModel.sent_at.desc(), WhatsAppMessageModel.id)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None, None
        content, sender_type = row
        return content[:_PREVIEW_CHARS], sender_type

    async def update_conversation_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None:
        await self._session.execute(
            sql_update(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.id == conversation_id,
                WhatsAppConversationModel.tenant_id == tenant_id,
            )
            .values(status=status)
        )
        await self._session.commit()

    async def close_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        stmt = (
            sql_update(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.id == conversation_id,
                WhatsAppConversationModel.tenant_id == tenant_id,
            )
            .values(status="closed", closed_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return await self.get_conversation(tenant_id, conversation_id)

    async def claim_conversation(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> WhatsAppConversation | None:
        """Atomic claim. `WHERE employee_id IS NULL` is the whole mechanism.

        Two simultaneous claims both issue this UPDATE; the database serialises them
        and the loser's `rowcount` is 0. A lock table would be a second source of
        truth for a fact the conversation row already holds.
        """
        stmt = (
            sql_update(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.id == conversation_id,
                WhatsAppConversationModel.tenant_id == tenant_id,
                WhatsAppConversationModel.employee_id.is_(None),
                WhatsAppConversationModel.status.in_(OPEN_CONVERSATION_STATUSES),
            )
            .values(employee_id=employee_id, status="human")
        )
        # `Session.execute` is typed as returning a plain Result; an UPDATE always
        # yields a CursorResult, and its rowcount is the whole point of this method.
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        if result.rowcount == 0:
            return None
        return await self.get_conversation(tenant_id, conversation_id)

    async def employee_id_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The acting employee behind a signed-in user, on the branch they are working.

        Claiming and replying are attributed to an *employee*, not a user: the same
        person can be an employee at two branches, and the inbox is branch-scoped.
        """
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.user_id == user_id,
            EmployeeModel.branch_id == branch_id,
            EmployeeModel.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def employee_display_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None:
        # `select_from(EmployeeModel)` is load-bearing: selecting only Person/User
        # columns makes SQLAlchemy guess the FROM, and employees ends up cross-joined.
        stmt = (
            select(PersonModel.first_name, PersonModel.last_name, UserModel.email)
            .select_from(EmployeeModel)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .join(PersonModel, PersonModel.id == EmployeeModel.person_id)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        first_name, last_name, email = row
        full = " ".join(part for part in (first_name, last_name) if part).strip()
        return full or email

    # --- Autoreply: ajustes, emisiones, token --------------------------------
    async def get_autoreply_settings(
        self, tenant_id: uuid.UUID
    ) -> AutoreplySettings | None:
        stmt = select(WhatsAppAutoreplySettingsModel).where(
            WhatsAppAutoreplySettingsModel.tenant_id == tenant_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _settings(row) if row else None

    async def upsert_autoreply_settings(
        self, settings: AutoreplySettings
    ) -> AutoreplySettings:
        stmt = select(WhatsAppAutoreplySettingsModel).where(
            WhatsAppAutoreplySettingsModel.tenant_id == settings.tenant_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = WhatsAppAutoreplySettingsModel(tenant_id=settings.tenant_id)
            self._session.add(row)
        row.greeting_enabled = settings.greeting_enabled
        row.greeting_open_text = settings.greeting_open_text
        row.greeting_closed_text = settings.greeting_closed_text
        row.greeting_awaiting_payment_text = settings.greeting_awaiting_payment_text
        row.assistant_offer_enabled = settings.assistant_offer_enabled
        row.idle_hours = settings.idle_hours
        row.token_lifetime_hours = settings.token_lifetime_hours
        row.status_mapping = settings.status_mapping
        row.faqs = (
            None if settings.faqs is None else [_faq_json(faq) for faq in settings.faqs]
        )
        row.quick_replies = (
            None
            if settings.quick_replies is None
            else [_quick_reply_json(entry) for entry in settings.quick_replies]
        )
        await self._session.commit()
        await self._session.refresh(row)
        return _settings(row)

    async def try_claim_emission(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        kind: str,
        conversation_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        customer_state: str | None = None,
        detail: str | None = None,
    ) -> bool:
        """Insert-or-ignore sobre la constraint. Gana uno, envía uno.

        La clave va COMPUESTA en una sola columna de texto porque en SQL dos NULL no son
        iguales: con la tupla de columnas, un aviso de estado (que no lleva conversación)
        nunca chocaría consigo mismo y saldría en cada rebote de la entrega.
        """
        dialect = self._session.bind.dialect.name if self._session.bind else "postgresql"
        insert = sqlite_insert if dialect == "sqlite" else pg_insert
        stmt = (
            insert(WhatsAppOutboundEmissionModel)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                branch_id=branch_id,
                kind=kind,
                dedupe_key=emission_key(
                    kind,
                    conversation_id=conversation_id,
                    order_id=order_id,
                    customer_state=customer_state,
                    detail=detail,
                ),
                conversation_id=conversation_id,
                order_id=order_id,
                customer_state=customer_state,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "dedupe_key"])
            .returning(WhatsAppOutboundEmissionModel.id)
        )
        won = (await self._session.execute(stmt)).scalar_one_or_none()
        await self._session.commit()
        return won is not None

    async def set_store_token(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> None:
        await self._session.execute(
            sql_update(WhatsAppConversationModel)
            .where(
                WhatsAppConversationModel.id == conversation_id,
                WhatsAppConversationModel.tenant_id == tenant_id,
            )
            .values(store_token=token, store_token_expires_at=expires_at)
        )
        await self._session.commit()

    async def find_conversation_by_token(
        self, token: str
    ) -> WhatsAppConversation | None:
        # Sin filtro de tenant: el token ES la credencial, como el instance_ref del webhook.
        # Es opaco y aleatorio, así que no se adivina.
        stmt = select(WhatsAppConversationModel).where(
            WhatsAppConversationModel.store_token == token
        )
        row = (
            await self._session.execute(stmt.execution_options(skip_tenant_filter=True))
        ).scalar_one_or_none()
        return _conversation(row) if row else None

    async def order_lines(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderLineSummary]:
        rows = (
            await self._session.execute(
                select(
                    ProductModel.name,
                    OrderItemModel.quantity,
                    OrderItemModel.line_subtotal,
                )
                .join(
                    ProductVariantModel,
                    ProductVariantModel.id == OrderItemModel.product_variant_id,
                )
                .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
                .where(
                    OrderItemModel.tenant_id == tenant_id,
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.status != "cancelled",
                )
                .order_by(OrderItemModel.created_at)
            )
        ).all()
        return [
            OrderLineSummary(name=r[0], quantity=r[1], line_subtotal=r[2]) for r in rows
        ]

    async def unsettled_orders_for_contact(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> list[UnsettledOrder]:
        """Los pedidos de este contacto a los que les falta plata, del más nuevo al más viejo.

        Aquí NO se filtra por método: un pedido que iba a pagarse en efectivo y quedó a medias
        también admite un comprobante. Lo que se exige es que falte plata y que sea de este
        contacto — esa segunda parte es la que impide que un id de otro cliente cuele.
        """
        paid = (
            select(func.coalesce(func.sum(OrderPaymentModel.amount), 0))
            .where(OrderPaymentModel.order_id == OrderModel.id)
            .correlate(OrderModel)
            .scalar_subquery()
        )
        stmt = (
            select(OrderModel.id, OrderModel.branch_id, OrderModel.total, paid)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.whatsapp_contact_id == contact_id,
                OrderModel.status.notin_(("closed", "cancelled")),
                OrderModel.created_at >= since,
                paid < OrderModel.total,
            )
            .order_by(OrderModel.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            UnsettledOrder(
                order_id=order_id, branch_id=branch_id, total=total, paid=paid_amount
            )
            for order_id, branch_id, total, paid_amount in rows
        ]

    async def orders_using_proofs(
        self, tenant_id: uuid.UUID, urls: list[str]
    ) -> dict[str, uuid.UUID]:
        """De estos archivos, cuáles ya son el comprobante de un pedido: `url → pedido`.

        Se DERIVA de los claims en vez de marcar el mensaje con una columna. La verdad de "este
        archivo ya se usó" es que existe un claim que apunta a él; una columna sería una segunda
        copia de ese hecho, y la que se quedaría vieja el día que alguien borre un claim.
        """
        if not urls:
            return {}
        stmt = select(
            OrderPaymentClaimModel.proof_url, OrderPaymentClaimModel.order_id
        ).where(
            OrderPaymentClaimModel.tenant_id == tenant_id,
            OrderPaymentClaimModel.proof_url.in_(urls),
        )
        rows = (await self._session.execute(stmt)).all()
        return {url: order_id for url, order_id in rows if url}

    async def find_message(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> WhatsAppMessage | None:
        stmt = select(WhatsAppMessageModel).where(
            WhatsAppMessageModel.id == message_id,
            WhatsAppMessageModel.tenant_id == tenant_id,
            WhatsAppMessageModel.whatsapp_conversation_id == conversation_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _message(row) if row else None

    async def unsettled_prepaid_order(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> OrderContext | None:
        """El pedido de este contacto que nació prepago y todavía debe plata.

        Es lo que elige la tercera variante del saludo, y se elige por ESTO —un hecho de la base—
        y no por lo que el cliente escribió: el saludo sigue sin leer el texto.

        "Debe" es `pagos < total`, la misma cuenta de la que ya cuelgan la verificación de cocina y
        el cierre. `cash` queda fuera porque se cobra en la puerta: no debe nada por adelantado.
        """
        paid = (
            select(func.coalesce(func.sum(OrderPaymentModel.amount), 0))
            .where(OrderPaymentModel.order_id == OrderModel.id)
            .correlate(OrderModel)
            .scalar_subquery()
        )
        stmt = (
            select(OrderModel.id, OrderModel.branch_id, OrderModel.total)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.whatsapp_contact_id == contact_id,
                OrderModel.status.notin_(("closed", "cancelled")),
                OrderModel.payment_method.is_not(None),
                OrderModel.payment_method != "cash",
                OrderModel.created_at >= since,
                paid < OrderModel.total,
            )
            .order_by(OrderModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        order_id, branch_id, total = row
        return OrderContext(order_id=order_id, branch_id=branch_id, total=total)

    async def has_live_order(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> bool:
        """¿Tiene este contacto un pedido sin terminar y reciente?

        Es el gate que separa "¿dónde están?" (una pregunta) de "mi dirección es la calle 5" (un
        cliente a mitad de un pedido). Sin él, una FAQ le contesta la dirección del restaurante a
        quien está dando la suya, y eso es indistinguible de un sistema roto.

        La ventana (`since`) no es prudencia: sin ella, un pedido abandonado hace tres semanas
        silencia las FAQs para siempre y nada lo explica.

        Sólo por contacto, nunca por cliente enlazado: lo único que se sabe con certeza es desde
        qué número escribió — mismo criterio que la herramienta "mis pedidos" del asistente.
        """
        stmt = (
            select(OrderModel.id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.whatsapp_contact_id == contact_id,
                OrderModel.status.notin_(("closed", "cancelled")),
                OrderModel.created_at >= since,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def order_context(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderContext | None:
        row = (
            await self._session.execute(
                select(
                    OrderModel.branch_id,
                    OrderModel.total,
                    OrderModel.whatsapp_contact_id,
                    OrderModel.customer_id,
                ).where(
                    OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
                )
            )
        ).one_or_none()
        if row is None:
            return None
        branch_id, total, contact_id, customer_id = row

        if contact_id is not None:
            phone = (
                await self._session.execute(
                    select(WhatsAppContactModel.phone).where(
                        WhatsAppContactModel.id == contact_id
                    )
                )
            ).scalar_one_or_none()
            return OrderContext(
                order_id=order_id,
                branch_id=branch_id,
                total=total,
                contact_id=contact_id if phone else None,
                phone=phone,
            )

        # Sin enlace directo: se busca por teléfono del cliente. Es la misma
        # identificación que usa el storefront (`find_or_create_by_phone`), así que un
        # pedido tomado por el mostrador a alguien que ya nos escribió también avisa.
        if customer_id is None:
            return OrderContext(order_id=order_id, branch_id=branch_id, total=total)
        phone = (
            await self._session.execute(
                select(PersonModel.phone)
                .join(CustomerModel, CustomerModel.person_id == PersonModel.id)
                .where(CustomerModel.id == customer_id)
            )
        ).scalar_one_or_none()
        if not phone:
            return OrderContext(order_id=order_id, branch_id=branch_id, total=total)
        contact = await self.find_contact_by_phone(tenant_id, phone)
        return OrderContext(
            order_id=order_id,
            branch_id=branch_id,
            total=total,
            contact_id=contact.id if contact else None,
            phone=contact.phone if contact else None,
        )

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        stmt = select(TenantModel.slug).where(TenantModel.id == tenant_id)
        return (
            await self._session.execute(stmt.execution_options(skip_tenant_filter=True))
        ).scalar_one_or_none()

    async def branch_code(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None:
        stmt = select(BranchModel.code).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def branch_name(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None:
        stmt = select(BranchModel.name).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def business_identity(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> BusinessIdentity:
        """El nombre del negocio y los datos de la sede, en una sola consulta.

        Una consulta y no dos porque esto va en el camino caliente del saludo, detrás de un
        mensaje que el cliente ya está esperando.
        """
        stmt = (
            select(
                TenantModel.name,
                BranchModel.name,
                BranchModel.address,
                BranchModel.phone,
            )
            .select_from(BranchModel)
            .join(TenantModel, TenantModel.id == BranchModel.tenant_id)
            .where(BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return BusinessIdentity(business_name="", branch_name="")
        business_name, branch_name, address, phone = row
        return BusinessIdentity(
            business_name=business_name or "",
            branch_name=branch_name or "",
            branch_address=address,
            branch_phone=phone,
        )

    async def branch_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[tuple[int, int, int]]:
        stmt = select(
            OperatingHoursModel.weekday,
            OperatingHoursModel.open_minute,
            OperatingHoursModel.close_minute,
        ).where(
            OperatingHoursModel.tenant_id == tenant_id,
            OperatingHoursModel.branch_id == branch_id,
        )
        return [(r[0], r[1], r[2]) for r in (await self._session.execute(stmt)).all()]

    # --- Messages ------------------------------------------------------------
    async def list_messages(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[WhatsAppMessage]:
        stmt = (
            select(WhatsAppMessageModel)
            .where(
                WhatsAppMessageModel.tenant_id == tenant_id,
                WhatsAppMessageModel.whatsapp_conversation_id == conversation_id,
            )
            .order_by(WhatsAppMessageModel.sent_at, WhatsAppMessageModel.id)
        )
        return [_message(m) for m in (await self._session.execute(stmt)).scalars()]

    async def last_outbound_content(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """Lo último que SALIÓ por este hilo, sea del sistema o de una persona.

        Lo entrante (`contact`) queda fuera del filtro, así que el mensaje que acaba de llegar
        no tapa la respuesta anterior. Sirve para no repetir un aviso automático: la verdad de
        "¿ya se dijo esto?" es el hilo, no un contador en memoria que un reinicio borra.
        """
        stmt = (
            select(WhatsAppMessageModel.content)
            .where(
                WhatsAppMessageModel.tenant_id == tenant_id,
                WhatsAppMessageModel.whatsapp_conversation_id == conversation_id,
                WhatsAppMessageModel.sender_type != "contact",
            )
            .order_by(WhatsAppMessageModel.sent_at.desc(), WhatsAppMessageModel.id.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def add_message(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        sender_type: str,
        content: str,
        employee_id: uuid.UUID | None = None,
        provider_message_id: str | None = None,
        delivery_state: str = "sent",
        media_type: str | None = None,
        media_mime: str | None = None,
    ) -> WhatsAppMessage:
        model = WhatsAppMessageModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            whatsapp_conversation_id=conversation_id,
            sender_type=sender_type,
            content=content,
            employee_id=employee_id,
            provider_message_id=provider_message_id,
            delivery_state=delivery_state,
            media_type=media_type,
            media_mime=media_mime,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _message(model)

    async def attach_media(
        self, tenant_id: uuid.UUID, message_id: uuid.UUID, media_url: str
    ) -> None:
        """Pega la URL del archivo a un mensaje YA guardado.

        Es un update y no parte del insert a propósito: el mensaje se guarda antes de tocar el
        archivo, así que un fallo bajándolo cuesta el archivo y nunca el mensaje. Invertir eso
        rompe la única garantía interesante de este camino.
        """
        await self._session.execute(
            sql_update(WhatsAppMessageModel)
            .where(
                WhatsAppMessageModel.id == message_id,
                WhatsAppMessageModel.tenant_id == tenant_id,
            )
            .values(media_url=media_url)
        )
        await self._session.commit()

    async def add_inbound_message_once(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        content: str,
        provider_message_id: str,
        provider_remote_jid: str | None = None,
        media_type: str | None = None,
        media_mime: str | None = None,
    ) -> WhatsAppMessage | None:
        """Insert-or-ignore on the unique `(tenant_id, provider_message_id)`.

        Done in the database rather than as a SELECT-then-INSERT: two redeliveries
        arriving at once would both find nothing and both insert. Returning None on
        conflict is what lets the webhook answer 200 without ringing the doorbell twice.

        `media_type` se guarda aunque el archivo no vaya a bajarse: es lo que permite que el hilo
        diga "llegó una imagen" cuando el puente no la devolvió. `provider_remote_jid` es lo que
        hace falta para pedírselo después, y por eso se guarda aquí y no se reconstruye.
        """
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "whatsapp_conversation_id": conversation_id,
            "sender_type": "contact",
            "content": content,
            "provider_message_id": provider_message_id,
            "provider_remote_jid": provider_remote_jid,
            "media_type": media_type,
            "media_mime": media_mime,
            "delivery_state": "sent",
        }
        dialect = self._session.bind.dialect.name if self._session.bind else "postgresql"
        insert = sqlite_insert if dialect == "sqlite" else pg_insert
        stmt = (
            insert(WhatsAppMessageModel)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "provider_message_id"]
            )
            .returning(WhatsAppMessageModel.id)
        )
        inserted_id = (await self._session.execute(stmt)).scalar_one_or_none()
        await self._session.commit()
        if inserted_id is None:
            return None
        row = (
            await self._session.execute(
                select(WhatsAppMessageModel).where(
                    WhatsAppMessageModel.id == inserted_id
                )
            )
        ).scalar_one()
        return _message(row)

    async def apply_delivery_report(
        self,
        tenant_id: uuid.UUID,
        provider_message_id: str,
        state: str,
    ) -> bool:
        """Sube el acuse de UN mensaje nuestro. `True` si el estado cambió de verdad.

        Se busca por `(tenant_id, provider_message_id)`, que ya tiene índice único —el mismo que
        hace idempotente la entrada—, así que no hace falta índice nuevo.

        Dos guardas que no son adorno:

        - **`sender_type == 'employee'`**: un acuse no puede tocar un mensaje del cliente ni
          aunque el id coincidiera. El sobre ya se filtró por `fromMe`, pero el que decide qué
          fila se escribe es este `WHERE`.
        - **`advance`**: el estado sólo sube. Los acuses llegan desordenados, y sin esto un
          `DELIVERY_ACK` tardío apaga un `read` que el cliente ya se ganó.

        Se lee y se escribe en dos pasos en vez de un `UPDATE ... WHERE rank < n` porque la escala
        vive en el dominio como función pura y probada; meterla en SQL la duplicaría en un dialecto
        que no se puede probar sin base.
        """
        row = (
            await self._session.execute(
                select(WhatsAppMessageModel).where(
                    WhatsAppMessageModel.tenant_id == tenant_id,
                    WhatsAppMessageModel.provider_message_id == provider_message_id,
                    WhatsAppMessageModel.sender_type == "employee",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        moved = advance(row.delivery_state, state)
        if moved == row.delivery_state:
            return False
        row.delivery_state = moved
        await self._session.commit()
        return True

    async def mark_delivery(
        self,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        delivery_state: str,
        provider_message_id: str | None = None,
    ) -> WhatsAppMessage | None:
        changes: dict[str, Any] = {"delivery_state": delivery_state}
        if provider_message_id is not None:
            changes["provider_message_id"] = provider_message_id
        await self._session.execute(
            sql_update(WhatsAppMessageModel)
            .where(
                WhatsAppMessageModel.id == message_id,
                WhatsAppMessageModel.tenant_id == tenant_id,
            )
            .values(**changes)
        )
        await self._session.commit()
        row = (
            await self._session.execute(
                select(WhatsAppMessageModel).where(
                    WhatsAppMessageModel.id == message_id,
                    WhatsAppMessageModel.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        return _message(row) if row else None
