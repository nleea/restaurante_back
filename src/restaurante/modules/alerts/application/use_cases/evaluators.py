"""Las tres reglas. Código con parámetros, no condiciones de texto libre.

Cada evaluador contesta lo mismo: **qué debe hablar** y **qué se ha recuperado de verdad**.
Las dos listas son igual de importantes. Sin la segunda una alerta se queda abierta para
siempre y ese sujeto no vuelve a poder avisar nunca — silencio permanente y sin síntoma, que
es peor que el ruido.

La histéresis vive aquí, no en el ciclo de vida, porque sólo aquí se sabe en qué unidad se mide
el colchón: **porcentaje del mínimo** para el stock, minutos para una caja abierta, puntos
porcentuales para la cuota, nada para una sesión caída. Es asimétrica a propósito: se dispara EN
el umbral y se re-arma sólo PASADO el umbral más el colchón. Con umbrales simétricos, un valor
oscilando en la frontera vuelve a avisar en cada evaluación, y eso es exactamente lo que hace que
alguien silencie el módulo.

El del stock es porcentual y no una cantidad porque **sus sujetos no comparten unidad de medida**:
son insumos, y cada uno lleva la suya. Un colchón fijo de 1 pedía un kilo entero de más sobre un
mínimo de 2 kg de camarón y un solo gramo sobre 500 g de sal — el mismo número, un 50% en un caso
y un 0,2% en el otro. Ningún valor absoluto puede ser correcto sobre cantidades incomparables, y
por eso nadie podía configurarlo bien.
"""

from __future__ import annotations

from datetime import UTC, datetime

from restaurante.modules.alerts.domain.entities import (
    RULE_ASSISTANT_QUOTA,
    RULE_CASH_SESSION_LEFT_OPEN,
    RULE_LOW_STOCK,
    RULE_WHATSAPP_SESSION_DOWN,
    AlertRule,
)
from restaurante.modules.alerts.domain.ports import (
    AssistantQuotaReader,
    CashReader,
    Evaluation,
    InventoryReader,
    SessionReader,
    Subject,
)
from restaurante.modules.business.application.clock import now_local


class LowStockEvaluator:
    """Un insumo por debajo de su mínimo.

    **No introduce un segundo umbral.** Inventario ya lleva `min_stock` por (sucursal,
    insumo) y una consulta que los encuentra; la regla añade el colchón de recuperación y
    nada más. Dos umbrales para un mismo concepto divergen en un mes, y entonces nadie sabe
    cuál manda.

    El sujeto es el insumo: quedarse sin tomate no puede tapar que también falta queso.
    """

    rule_key = RULE_LOW_STOCK

    def __init__(self, inventory: InventoryReader) -> None:
        self._inventory = inventory

    async def evaluate(
        self, rule: AlertRule, subject_ref: str | None = None, open_refs: list[str] | None = None
    ) -> Evaluation:
        firing: list[Subject] = []
        for stock in await self._inventory.low_stock(rule.tenant_id, rule.branch_id):
            if subject_ref and stock.ingredient_id != subject_ref:
                continue
            # Un insumo sin mínimo configurado no puede estar "bajo": 0 <= 0 sería siempre
            # cierto y avisaría de cada insumo del catálogo el día que se enciende la regla.
            if stock.minimum <= 0:
                continue
            firing.append(
                Subject(
                    ref=stock.ingredient_id,
                    label=stock.name,
                    detail=f"quedan {_num(stock.current)} (mínimo {_num(stock.minimum)})",
                )
            )

        cleared: list[str] = []
        candidates = [r for r in (open_refs or []) if not subject_ref or r == subject_ref]
        if candidates:
            levels = await self._inventory.stock_for(
                rule.tenant_id, rule.branch_id, candidates
            )
            for stock in levels:
                # Recuperado = por encima del mínimo más el colchón, y el colchón es un
                # **PORCENTAJE de ese mínimo**, no una cantidad.
                #
                # Tiene que serlo porque el sujeto de esta regla es el insumo y cada insumo lleva
                # su propia `unit_of_measure_id`: una cantidad fija significaría cosas distintas
                # para cada uno. Con el `1` absoluto que había antes, el mismo colchón pedía un
                # kilo entero de más sobre un mínimo de 2 kg de camarón (un 50%) y un solo gramo
                # sobre 500 g de sal (un 0,2%, que no protege de nada). No existe ningún número
                # absoluto que sea correcto para los dos, y por eso nadie podía configurarlo.
                #
                # Un porcentaje no tiene unidad por construcción y escala solo con cada insumo.
                #
                # Volver justo al mínimo sigue sin re-armar: ahí la condición que disparó
                # (`current <= minimum`) todavía es cierta.
                if stock.current > stock.minimum * (1 + rule.recovery_buffer / 100):
                    cleared.append(stock.ingredient_id)
        return Evaluation(firing=firing, cleared=cleared)


class WhatsAppSessionDownEvaluator:
    """El número de la sucursal dejó de recibir.

    Es la regla que cierra el hueco que `whatsapp-channel` dejó abierto a propósito: una
    sesión caída deja la sucursal MUDA y hoy sólo se nota entrando a la pantalla de números.

    Inerte cuando la sucursal no tiene sesiones: un negocio que no usa WhatsApp no puede
    recibir alertas de que su WhatsApp está caído.
    """

    rule_key = RULE_WHATSAPP_SESSION_DOWN

    def __init__(self, sessions: SessionReader) -> None:
        self._sessions = sessions

    async def evaluate(
        self, rule: AlertRule, subject_ref: str | None = None, open_refs: list[str] | None = None
    ) -> Evaluation:
        firing: list[Subject] = []
        cleared: list[str] = []
        for session in await self._sessions.sessions(rule.tenant_id, rule.branch_id):
            if subject_ref and session.session_id != subject_ref:
                continue
            if session.connected:
                # No hay colchón que aplicar: "conectada" no es un número que oscile en un
                # umbral, es un estado. Reconectar re-arma, y punto.
                cleared.append(session.session_id)
            else:
                firing.append(
                    Subject(
                        ref=session.session_id,
                        label=session.label,
                        detail="el número no está recibiendo mensajes",
                    )
                )
        return Evaluation(firing=firing, cleared=cleared)


class CashSessionLeftOpenEvaluator:
    """La caja sigue abierta pasada la hora en que ya no debería.

    `threshold` es la hora del día (0–23) a partir de la cual dejar la caja abierta es un
    problema; el colchón se mide en minutos y evita que una caja abierta justo en la frontera
    dispare y se cierre en bucle.

    Se mira en HORA LOCAL del negocio: comparar contra UTC en Colombia declararía "las 2 de
    la madrugada" a las 9 de la noche.
    """

    rule_key = RULE_CASH_SESSION_LEFT_OPEN
    DEFAULT_HOUR = 23

    def __init__(self, cash: CashReader) -> None:
        self._cash = cash

    async def evaluate(
        self, rule: AlertRule, subject_ref: str | None = None, open_refs: list[str] | None = None
    ) -> Evaluation:
        session = await self._cash.open_session(rule.tenant_id, rule.branch_id)
        hour = int(rule.threshold if rule.threshold is not None else self.DEFAULT_HOUR)
        now = now_local()

        if session is None:
            # La caja se cerró: lo que estuviera abierto ya no lo está, así que todo lo que
            # tenía alerta se recupera. Es la única regla cuyo "cleared" no mira un valor.
            return Evaluation(cleared=list(open_refs or []))

        if subject_ref and session.session_id != subject_ref:
            return Evaluation()

        opened = _as_local(session.opened_at)
        # Y que lleve abierta más que el colchón, para que abrir la caja a las 23:01 no
        # dispare en el mismo minuto en que alguien la está abriendo.
        minutes_open = (now - opened).total_seconds() / 60
        if now.hour >= hour and minutes_open >= rule.recovery_buffer:
            return Evaluation(
                firing=[
                    Subject(
                        ref=session.session_id,
                        label="Caja",
                        detail=f"abierta desde las {opened.hour:02d}:{opened.minute:02d}",
                    )
                ]
            )
        return Evaluation()


class AssistantQuotaEvaluator:
    """El saldo del asistente pasó del umbral que el dueño puso.

    El umbral vive en el DERECHO del tenant (`warning_threshold_percent`), no en el
    `threshold` de la regla: quien vende el saldo es quien sabe a qué altura conviene avisar,
    y tener dos números para lo mismo es cómo acaban discrepando.

    Se re-arma solo al empezar el periodo siguiente, porque el consumo vuelve a cero y cae
    por debajo del umbral menos el colchón. No hace falta ninguna lógica de "es otro mes":
    la histéresis de siempre ya lo hace.

    Un sujeto por tenant, no por sucursal. La cuota se compra por negocio, así que avisar por
    sede sería contar tres veces el mismo dinero.
    """

    rule_key = RULE_ASSISTANT_QUOTA

    def __init__(self, assistant: AssistantQuotaReader) -> None:
        self._assistant = assistant

    async def evaluate(
        self, rule: AlertRule, subject_ref: str | None = None, open_refs: list[str] | None = None
    ) -> Evaluation:
        level = await self._assistant.quota(rule.tenant_id)
        if level is None:
            # Sin derecho no hay saldo: la regla existe pero no tiene de qué hablar.
            return Evaluation(cleared=list(open_refs or []))

        ref = str(rule.tenant_id)
        if subject_ref and subject_ref != ref:
            return Evaluation()

        # El umbral de la regla es un OVERRIDE; sin él manda el del derecho, que es donde el
        # dueño lo puso al comprar el saldo.
        limit = (
            float(rule.threshold)
            if rule.threshold is not None
            else float(level.warning_threshold_percent)
        )
        if level.used_percent >= limit:
            return Evaluation(
                firing=[
                    Subject(
                        ref=ref,
                        label="Saldo del asistente",
                        detail=(
                            f"gastado el {_num(level.used_percent)}% "
                            f"({level.used_units} de {level.quota_units})"
                        ),
                    )
                ]
            )
        # Recuperado = por debajo del umbral MENOS el colchón. Volver justo al umbral no
        # re-arma: la siguiente pregunta lo cruzaría otra vez.
        if level.used_percent < limit - rule.recovery_buffer:
            return Evaluation(cleared=list(open_refs or []))
        return Evaluation()


def _as_local(value: datetime) -> datetime:
    """Un instante guardado (UTC) en la hora del negocio; SQLite lo devuelve sin zona."""
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(now_local().tzinfo)


def _num(value: float) -> str:
    """`2.0` → "2", `2.5` → "2.5". Un mensaje al dueño no dice "quedan 2.000 kg"."""
    return f"{value:g}"


def build_registry(
    inventory: InventoryReader | None = None,
    sessions: SessionReader | None = None,
    cash: CashReader | None = None,
    assistant: AssistantQuotaReader | None = None,
) -> dict[str, object]:
    """`rule_key` → evaluador.

    Es un registro y no un `if/elif` para que `assistant-core` pueda añadir la regla de
    cuota sin tocar nada de aquí. Un lector ausente deja su regla fuera: el módulo tiene que
    funcionar con WhatsApp completamente ausente.
    """
    registry: dict[str, object] = {}
    if inventory is not None:
        registry[RULE_LOW_STOCK] = LowStockEvaluator(inventory)
    if sessions is not None:
        registry[RULE_WHATSAPP_SESSION_DOWN] = WhatsAppSessionDownEvaluator(sessions)
    if cash is not None:
        registry[RULE_CASH_SESSION_LEFT_OPEN] = CashSessionLeftOpenEvaluator(cash)
    if assistant is not None:
        registry[RULE_ASSISTANT_QUOTA] = AssistantQuotaEvaluator(assistant)
    return registry
