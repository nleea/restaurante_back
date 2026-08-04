"""Los puertos del asistente. Aquí es donde se decide que LangChain no exista.

`ConversationEngine` toma y devuelve **dataclasses nuestras**. Ni un `AIMessage` ni un
`Runnable` cruzan esta línea, y eso no es purismo: el `mypy` override que necesita el paquete
`infrastructure/llm/` sólo es honesto mientras nada de allí escape. Si un tipo de LangChain
sube a `application/`, el override deja de ser una excepción acotada y pasa a ser un agujero
en un código estricto.

`KnowledgeIndex` se va a la calle con un adaptador inerte, igual que `NullEventPublisher`. No
hay corpus todavía; lo que sí hay es la certeza de que **al índice no se le pregunta lo que
sabe la base de datos**. El stock, las ventas, la carta y los horarios se contestan llamando a
casos de uso, porque un informe incrustado produce un bot que afirma con seguridad los
números de la semana pasada.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.assistant.domain.entities import (
    AssistantConversationState,
    AssistantEntitlement,
    ConversationTurn,
    UsageEntry,
)


# --- Herramientas ----------------------------------------------------------------------
@dataclass
class ToolSpec:
    """Un caso de uso ya existente, presentado para que el modelo pueda pedirlo.

    `run` recibe los argumentos que el modelo propone y devuelve texto. La herramienta ya
    viene atada al llamador (su tenant, su sucursal, sus permisos) cuando se construye el
    registro: el modelo nunca recibe una credencial, recibe un conjunto de cosas que ya puede
    hacer.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], Awaitable[str]]


# --- El motor --------------------------------------------------------------------------
@dataclass
class EngineRequest:
    """Todo lo que hace falta para una llamada, sin nada del proveedor dentro."""

    provider: str
    model: str
    system_prompt: str
    question: str
    turns: list[ConversationTurn] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    max_output_tokens: int = 512
    #: Viaja como texto, no como un tipo del proveedor: el motor sólo tiene que saber cuánto
    #: se le deja pensar, no de qué SDK salió esa palabra.
    reasoning_effort: str = "none"


@dataclass
class EngineReply:
    """Lo que contestó, y lo que costó decirlo.

    Los tokens vienen del proveedor y no de una estimación nuestra: son la única cifra con la
    que se puede auditar una factura.
    """

    text: str
    tokens_in: int
    tokens_out: int


class ConversationEngine(Protocol):
    async def respond(self, request: EngineRequest) -> EngineReply: ...


# --- El índice -------------------------------------------------------------------------
@dataclass
class Passage:
    """Un trozo de prosa recuperado. Hoy no hay ninguno."""

    text: str
    source: str


class KnowledgeIndex(Protocol):
    async def retrieve(
        self, tenant_id: uuid.UUID, query: str, limit: int = 4
    ) -> list[Passage]: ...


class NullKnowledgeIndex:
    """El adaptador inerte. Devuelve nada y el asistente contesta con herramientas.

    Es la misma forma que `NullEventPublisher`: el puerto viaja desde el primer día para que
    el día que exista un pgvector detrás no haya que tocar ni un caso de uso.
    """

    async def retrieve(
        self, tenant_id: uuid.UUID, query: str, limit: int = 4
    ) -> list[Passage]:
        return []


# --- Persistencia ----------------------------------------------------------------------
class AssistantRepository(Protocol):
    async def get_entitlement(
        self, tenant_id: uuid.UUID
    ) -> AssistantEntitlement | None: ...

    async def save_entitlement(
        self, entitlement: AssistantEntitlement
    ) -> AssistantEntitlement: ...

    async def record_usage(self, entry: UsageEntry) -> UsageEntry: ...

    async def units_used(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> int:
        """El saldo es una PROYECCIÓN sobre el libro, no un contador que baja."""
        ...

    async def usage_cost(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> Decimal: ...

    async def recent_usage(
        self, tenant_id: uuid.UUID, limit: int = 20
    ) -> list[UsageEntry]: ...

    async def get_state(
        self, tenant_id: uuid.UUID, conversation_ref: str
    ) -> AssistantConversationState | None: ...

    async def save_state(
        self, state: AssistantConversationState
    ) -> AssistantConversationState: ...


class ConversationChannel(Protocol):
    """Por dónde le llega la respuesta al cliente, y cómo se marca la conversación.

    Es un puerto y no un import de messaging por la misma razón que el escalado de alertas:
    el asistente tiene que poder existir con WhatsApp completamente ausente. Sin adaptador
    enchufado no hay vía de cliente y el chat de administración funciona igual.
    """

    async def send(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool: ...

    async def set_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None: ...

    async def store_link(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str: ...

    async def last_outbound_text(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """Lo último que SALIÓ por este hilo, o `None` si aún no salió nada.

        Existe para no repetir un aviso automático que ya se dio. Se pregunta al hilo y no a
        un contador propio a propósito: el hilo es la verdad, sobrevive a un reinicio y no se
        desincroniza cuando quien contesta es otro proceso.
        """
        ...


class OpeningHoursReader(Protocol):
    """¿Hay alguien detrás ahora mismo, y si no, cuándo lo habrá?

    Puerto y no un import de `business` por lo mismo que el canal: el asistente tiene que
    poder existir sin él. Sin adaptador enchufado contesta a cualquier hora, que es como se
    comportaba antes de que el horario le importara.

    Devuelve `(abierto, próxima apertura como (día, minuto))`. El día es 0=lunes, igual que en
    el resto del sistema.
    """

    async def status(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> tuple[bool, tuple[int, int] | None]: ...


class RateLimiter(Protocol):
    async def hit(self, tenant_id: uuid.UUID, limit_per_minute: int) -> bool:
        """`True` si esta llamada cabe en el minuto. Rechazar no consume cuota."""
        ...
