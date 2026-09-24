"""A quién se le publica un estado, y por qué la lista es más corta de lo que el dueño espera.

Aquí está el riesgo entero del change. Publicar un estado a N contactos son N/10 llamadas a
`status@broadcast` —el puente parte en tandas de diez— y ese número es el que puede costar la cuenta
de WhatsApp del negocio. Si el número cae, cae el canal completo: bandeja, avisos de pedido,
asistente. No sólo esta pantalla.

De ahí que las cuatro reducciones existan desde el primer día y no "para después", y de que la
lógica viva en una función **pura**: es lo único que permite probar la tabla del diseño
—340 → 12 → 4 → 118 → tope 200 → 6 omitidos— sin levantar una base.

Dos propiedades que no son obvias:

**Cada contacto cuenta en exactamente UN cubo**, el primero que lo excluye. Un `@lid` que además
pidió no recibir se cuenta como `@lid` y no en los dos. Si se contara doble, los números no sumarían
con el total y una lista itemizada que no cuadra no se puede leer — que es justo lo que este módulo
tiene que evitar, porque un "publicado a 200" sobre 340 se lee como cobertura completa.

**El tope muerde AL FINAL.** Es la red de seguridad, no el criterio: la ventana de inactividad es la
que de verdad quita riesgo, porque quien escribió una vez hace ocho meses ya borró el chat y es
volumen de salida sin audiencia posible detrás. El tope, en cambio, sí quita espectadores reales, y
por eso es lo último y lo único que se anuncia como *omitido*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from restaurante.shared.domain.phones import normalize_phone

#: El sufijo de un JID de WhatsApp corriente.
#:
#: Sí, esto es reconstruir un JID, y reconstruir un JID ya fue una de las trampas conocidas del
#: canal (ver el comentario de `WhatsAppMessageModel.provider_remote_jid`). Aquí no hay alternativa:
#: `provider_remote_jid` se guarda por MENSAJE y una audiencia son CONTACTOS, así que no existe
#: ninguna columna con el JID del contacto que se pueda leer en su lugar.
WHATSAPP_JID_SUFFIX = "@s.whatsapp.net"

#: Techo absoluto de destinatarios por publicación, **por encima de cualquier ajuste**.
#:
#: Es una constante del dominio y no un setting a propósito: un techo configurable no es un techo.
#: 500 son 50 llamadas a `status@broadcast` en una tanda, que ya es más de lo que ningún restaurante
#: necesita y bastante más de lo que conviene pedirle a un puente no oficial.
ABSOLUTE_RECIPIENT_CEILING = 500


@dataclass(frozen=True)
class StatusCandidate:
    """Un contacto que escribió a esta sede, tal y como sale de la consulta.

    `address` es el `phone` del contacto, que puede ser un número o un `@lid` — el repositorio no
    interpreta, sólo trae. `last_inbound_at` es su último mensaje ENTRANTE en esta sede: no vale el
    último mensaje del hilo, porque una respuesta nuestra de ayer no dice nada de si esa persona
    sigue ahí.
    """

    address: str
    last_inbound_at: datetime
    opted_out: bool


@dataclass(frozen=True)
class StatusAudience:
    """La lista final y el porqué de cada baja.

    Las cuatro exclusiones son campos separados y no una suma porque un total no puede responder la
    única pregunta que importa antes de publicar: *por qué* bajó de 340 a 200. Y `excluded_by_cap`
    mayor que cero es lo único que distingue "esto llegó a todos los que podía" de "esto se truncó".
    """

    jids: list[str]
    total_candidates: int
    excluded_no_number: int
    excluded_opted_out: int
    excluded_inactive: int
    excluded_by_cap: int

    @property
    def addressed_count(self) -> int:
        """A cuántos se DIRIGE. No a cuántos llega — eso no se puede saber."""
        return len(self.jids)

    @property
    def is_empty(self) -> bool:
        return not self.jids


def is_privacy_jid(address: str) -> bool:
    """Un `@lid` (o cualquier JID) en vez de un número.

    `normalize_phone` devuelve estas direcciones intactas a propósito, porque para un mensaje
    directo son lo único con lo que se le puede escribir a ese contacto. Para `statusJidList` es un
    desconocido, y el modo de fallo es el peor posible: el puente mete el `@lid` en una tanda, la
    tanda falla, `Promise.allSettled` se come el error y Evolution devuelve 201. "Publicado ✓" y
    nadie lo recibió.

    Un fallo que se presenta como éxito no se puede diagnosticar, así que se excluyen **y se
    cuentan**. Excluir a alguien de forma visible siempre gana a incluirlo y fallar callado.
    """
    return "@" in address


def to_jid(address: str) -> str:
    """`573001112233` → `573001112233@s.whatsapp.net`. Sólo para direcciones que son un número."""
    return f"{normalize_phone(address)}{WHATSAPP_JID_SUFFIX}"


def with_own_jid(jids: list[str], own_phone: str | None) -> list[str]:
    """La lista que se ENVÍA: la audiencia más el número propio de la sesión, al frente.

    Evolution sólo manda el estado a los JIDs de `statusJidList`, y eso incluye al propio
    teléfono: sin su JID en la lista, "Mi estado" del restaurante queda vacío aunque el puente
    devuelva 201. Por eso se agrega aquí, y por eso es una lista aparte de `StatusAudience.jids` —
    el número propio no es un destinatario, así que no cuenta en `addressed_count` ni en el tope.

    Sin número (`None` o un `@lid`) devuelve la audiencia tal cual; nunca se duplica.
    """
    if not own_phone:
        return list(jids)
    if is_privacy_jid(own_phone):
        if not own_phone.endswith(WHATSAPP_JID_SUFFIX):
            return list(jids)
        own = own_phone
    else:
        own = to_jid(own_phone)
    return [own, *(jid for jid in jids if jid != own)]


def effective_cap(configured_cap: int) -> int:
    """El tope que de verdad aplica: el ajuste, pero nunca por encima del techo del dominio.

    Un ajuste a 5000 no publica a 5000. Es la propiedad que hace que el techo sea un techo.
    """
    return max(0, min(configured_cap, ABSOLUTE_RECIPIENT_CEILING))


def resolve_audience(
    candidates: list[StatusCandidate],
    *,
    now: datetime,
    inactivity_days: int,
    configured_cap: int,
) -> StatusAudience:
    """Las cuatro reducciones, en orden, con su cuenta cada una.

    Espera `candidates` **ya ordenados por actividad reciente descendente** — es la consulta la que
    ordena, y ese orden es un requisito y no una comodidad: es lo que hace que, cuando el tope tenga
    que dejar gente fuera, los que se queden sean los que escribieron hace menos. Cortar una lista
    sin orden deja un subconjunto arbitrario, que es lo mismo que elegir al azar quién ve el menú.

    El orden de las reducciones también importa, y es el del spec: primero quien no puede recibirlo
    (`@lid`), luego quien no quiere (opt-out), luego quien probablemente ya no está (inactivo), y
    sólo al final el tope. Cada contacto cae en el primer cubo que lo excluye y en ninguno más, así
    que `total = dirigidos + las cuatro exclusiones` siempre cuadra.
    """
    cutoff = now - timedelta(days=inactivity_days)
    cap = effective_cap(configured_cap)

    no_number = 0
    opted_out = 0
    inactive = 0
    eligible: list[str] = []

    for candidate in candidates:
        if is_privacy_jid(candidate.address):
            no_number += 1
            continue
        if candidate.opted_out:
            opted_out += 1
            continue
        if candidate.last_inbound_at < cutoff:
            inactive += 1
            continue
        eligible.append(to_jid(candidate.address))

    # El tope, al final y sobre una lista ya ordenada por recencia.
    by_cap = max(0, len(eligible) - cap)
    addressed = eligible[:cap]

    return StatusAudience(
        jids=addressed,
        total_candidates=len(candidates),
        excluded_no_number=no_number,
        excluded_opted_out=opted_out,
        excluded_inactive=inactive,
        excluded_by_cap=by_cap,
    )


def publication_calls(addressed: int, provider_batch_size: int = 10) -> int:
    """Cuántas llamadas a `status@broadcast` provoca UNA publicación de `addressed` destinatarios.

    No parte nada: cuenta. Existe porque es el número que mide el riesgo —200 destinatarios son 20
    llamadas— y tenerlo como función deja el cálculo en un sitio en vez de en un comentario.

    **Y deja escrito por qué nosotros NO partimos la lista.** Evolution ya la parte en tandas de
    diez y reenvía cada tanda con el MISMO `messageId`, que es lo que hace que el espectador vea una
    sola historia (`whatsapp.baileys.service.ts:2271`). Si partiéramos aquí, cada llamada nuestra
    sería una publicación distinta con su propio id: 200 destinatarios se convertirían en **20
    historias idénticas** en la pestaña de novedades de cada contacto. Se manda UNA llamada con la
    lista entera; el troceado es cosa del puente.
    """
    if provider_batch_size <= 0:
        return 1 if addressed else 0
    return -(-addressed // provider_batch_size)
