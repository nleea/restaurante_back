"""Evaluar reglas: el job (latencia) y el barrido (garantía).

Copiado a propósito del worker de domicilios, incluida su postura: **el sistema tiene que
ser correcto con el camino del job completamente eliminado.**

- `evaluate_rule` con un sujeto → es el job, anunciado tras la mutación que pudo cambiar la
  condición. Da segundos de latencia y puede perderse: Redis caído, el job murió, un camino
  de código que se olvidó de anunciar.
- `sweep` → recorre TODAS las reglas encendidas de TODOS los tenants y sucursales. Es
  autoritativo. Encuentra lo que el job no encontró, tarde pero seguro.

Certero-y-tarde le gana a rápido-y-ausente: una alerta que llega un barrido más tarde sigue
sirviendo; una que no llega nunca es el módulo entero sin sentido.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from restaurante.modules.alerts.application.use_cases.lifecycle import AlertLifecycle
from restaurante.modules.alerts.domain.entities import AlertRule
from restaurante.modules.alerts.domain.ports import (
    AlertRepository,
    AlertRuleEvaluator,
    Subject,
)

logger = logging.getLogger(__name__)


@dataclass
class SweepResult:
    """Qué hizo una pasada. Se devuelve para poder registrarlo y probarlo."""

    rules_evaluated: int = 0
    fired: int = 0
    resolved: int = 0
    #: Avisos repetidos por el panel de alertas que seguían abiertas y sin tocar.
    reminded: int = 0
    escalated: int = 0


class AlertSweeper:
    def __init__(
        self,
        repo: AlertRepository,
        lifecycle: AlertLifecycle,
        evaluators: dict[str, AlertRuleEvaluator],
    ) -> None:
        self._repo = repo
        self._lifecycle = lifecycle
        self._evaluators = evaluators

    async def evaluate_rule(
        self,
        rule: AlertRule,
        subject_ref: str | None = None,
        labels: dict[str, Subject] | None = None,
    ) -> SweepResult:
        """Mira una regla y actúa. Es el cuerpo compartido por el job y el barrido.

        Que sea el MISMO código en los dos caminos no es ahorro de líneas: es lo que hace
        que "el barrido es autoritativo" sea cierto en vez de una aspiración. Dos
        implementaciones divergen, y la que casi nunca corre es la que se rompe en silencio.
        """
        result = SweepResult(rules_evaluated=1)
        evaluator = self._evaluators.get(rule.rule_key)
        if evaluator is None or not rule.is_enabled:
            # Una regla apagada no se evalúa siquiera: encenderla es una decisión del dueño,
            # y sin evaluador (p. ej. sin WhatsApp instalado) la regla simplemente no existe.
            return result

        open_alerts = [
            a
            for a in await self._repo.list_open(rule.tenant_id, rule.branch_id)
            if a.rule_key == rule.rule_key
        ]
        open_refs = [a.subject_ref for a in open_alerts]

        try:
            evaluation = await evaluator.evaluate(rule, subject_ref, open_refs)
        except Exception:  # noqa: BLE001
            # Una regla que revienta no puede llevarse la pasada entera: las demás
            # sucursales siguen necesitando sus alertas.
            logger.warning(
                "La regla %s falló al evaluar (tenant %s, sucursal %s)",
                rule.rule_key,
                rule.tenant_id,
                rule.branch_id,
                exc_info=True,
            )
            return result

        for subject in evaluation.firing:
            # Se guarda cómo se llama esto AHORA. Es lo que hace que un escalado media hora
            # después diga "Tomate" y no un uuid: la alerta sólo guarda la referencia, y
            # quien sabe traducirla es el evaluador que acaba de mirarla.
            if labels is not None:
                labels[subject.ref] = subject
            fired = await self._lifecycle.fire(
                rule.tenant_id, rule.branch_id, rule.rule_key, subject
            )
            if fired is not None:
                result.fired += 1

        if evaluation.cleared:
            result.resolved += await self._lifecycle.resolve_cleared(
                rule.tenant_id, rule.branch_id, rule.rule_key, evaluation.cleared
            )
        return result

    async def sweep(self) -> SweepResult:
        """La pasada autoritativa: todas las reglas encendidas, de todos los tenants.

        Sin filtro por "activos recientemente" a propósito. La sucursal que lleva dos días
        sin actividad es exactamente la que hay que mirar: puede que lleve dos días muda.
        """
        total = SweepResult()
        # Las etiquetas se recogen mientras se barre, no después: el evaluador ya las
        # calculó y volver a preguntarlas sería pagar dos veces la misma consulta.
        labels: dict[str, Subject] = {}
        for rule in await self._repo.list_enabled_rules():
            outcome = await self.evaluate_rule(rule, labels=labels)
            total.rules_evaluated += outcome.rules_evaluated
            total.fired += outcome.fired
            total.resolved += outcome.resolved
        # Recordar y escalar van al FINAL, cuando ya se sabe qué sigue encendido: una alerta
        # que se acaba de resolver en esta misma pasada no debe recordarse ni escalarse.
        #
        # Los dos usan las etiquetas recién calculadas, así que el aviso dice "Azúcar" y no un
        # uuid — que era el punto de recogerlas mientras se barre.
        total.reminded = await self._lifecycle.remind_pending(labels)
        total.escalated = await self._lifecycle.escalate_pending(labels)
        return total

    async def evaluate_subject(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
    ) -> SweepResult:
        """El camino del job: una regla, un sujeto. Latencia, no garantía."""
        rule = await self._repo.get_rule(tenant_id, branch_id, rule_key)
        if rule is None:
            return SweepResult()
        return await self.evaluate_rule(rule, subject_ref)


