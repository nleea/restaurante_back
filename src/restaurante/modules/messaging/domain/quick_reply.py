"""Respuestas rápidas: las frases que el negocio repite, guardadas para no reescribirlas.

**Esto no contesta nada.** Es lo único que hay que entender de este fichero, y es lo que lo separa
de su vecino `faq.py` pese a que se parezcan en la forma. Una FAQ la dispara el sistema leyendo lo
que escribió el cliente; una respuesta rápida la mete una persona en el compositor y esa persona
pulsa enviar. Por eso aquí no hay gates de estado, ni gate de pedido vivo, ni emisión única, ni
vocabulario reservado: todas esas defensas existen en `faq.py` porque allí el sistema hablaba solo,
y aquí no habla nadie que no sea un empleado mirando el hilo.

De eso salen las dos decisiones de forma:

1. **`{id, name, text}` y nada más.** Se caen los dos campos de `FaqEntry` que sólo significan algo
   cuando algo dispara solo. `enabled`: una FAQ apagada existe y no dispara; una plantilla no
   dispara nunca, así que "apagada" sólo podría querer decir "no la enseñes" y para eso está
   borrarla. `triggers`: sólo tienen sentido leyendo el mensaje del cliente, y aquí no se lee nada.
2. **Ningún marcador, y se rechaza al guardar.** El compositor mete texto en un `textarea`, no
   resuelve plantillas, así que un `{nombre}` guardado saldría por WhatsApp con las llaves puestas.
   Ver `reject_placeholders`.

Funciones puras: sin base de datos, sin red, sin reloj. Mismo criterio que `templates.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from restaurante.modules.messaging.domain.entities import QuickReply
from restaurante.modules.messaging.domain.templates import unknown_placeholders
from restaurante.shared.domain.errors import ValidationError

# Lo que cabe en un popover sin scroll infinito y sin perder el pulgar. No es un límite técnico:
# veinte frases distintas ya son más de las que nadie recuerda buscar.
MAX_QUICK_REPLIES = 20
# Muy por debajo de `MAX_REPLY_CHARS` (4096) a propósito: una plantilla es una frase, no un
# folleto, y el compositor tiene que poder recibir dos seguidas sin acercarse al límite de envío.
MAX_QUICK_REPLY_CHARS = 1000
# El nombre es la etiqueta del botón, no un título. Si no cabe en el popover, no sirve de etiqueta.
MAX_QUICK_REPLY_NAME_CHARS = 40


def reject_placeholders(text: str, where: str) -> None:
    """Cualquier `{loquesea}` es un error aquí, y el mensaje explica por qué.

    El conjunto permitido es **vacío**, así que `unknown_placeholders` marca todo lo que encuentre.
    No es que estos marcadores no existan —`{menu_link}` existe y lo resuelve el saludo—: es que
    este texto no pasa por `render` en ningún momento del camino, porque el camino es
    "el empleado lo ve en el compositor y pulsa enviar".

    Se rechaza AL GUARDAR, con el dueño mirando la pantalla, y no al enviar: descubrir que la
    plantilla sale con llaves en un chat real es la clase de fallo que ya no tiene arreglo.
    """
    unknown = unknown_placeholders(text, frozenset())
    if unknown:
        offenders = ", ".join(f"{{{name}}}" for name in sorted(unknown))
        raise ValidationError(
            f"{where}: las respuestas rápidas no rellenan marcadores, así que {offenders} "
            "saldría tal cual en el chat del cliente. Escribe el dato o quítalo."
        )


def validate_quick_replies(entries: Sequence[QuickReply]) -> None:
    """Todo lo que puede estar mal en una plantilla, dicho al guardar y nombrando a la culpable.

    Misma postura que `_validate_faqs`: un 422 que dice "datos inválidos" no arregla nada cuando
    hay veinte tarjetas en la pantalla.
    """
    if len(entries) > MAX_QUICK_REPLIES:
        raise ValidationError(
            f"Demasiadas respuestas rápidas: el máximo son {MAX_QUICK_REPLIES} y llegaron "
            f"{len(entries)}. Borra las que ya no uses."
        )
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        where = (
            f'Respuesta rápida "{entry.name.strip()}"'
            if entry.name.strip()
            else f"Respuesta rápida #{index}"
        )
        if not entry.id.strip():
            raise ValidationError(f"{where}: falta el identificador.")
        if entry.id in seen:
            raise ValidationError(f"{where}: identificador repetido ({entry.id}).")
        seen.add(entry.id)
        if not entry.name.strip():
            raise ValidationError(f"{where}: ponle un nombre para reconocerla.")
        if len(entry.name) > MAX_QUICK_REPLY_NAME_CHARS:
            raise ValidationError(
                f"{where}: el nombre pasa de {MAX_QUICK_REPLY_NAME_CHARS} caracteres. "
                "Es la etiqueta del botón, no el mensaje."
            )
        if not entry.text.strip():
            raise ValidationError(f"{where}: necesita un texto que insertar.")
        if len(entry.text) > MAX_QUICK_REPLY_CHARS:
            raise ValidationError(
                f"{where}: el texto pasa de {MAX_QUICK_REPLY_CHARS} caracteres."
            )
        reject_placeholders(entry.text, where)


# Las sugeridas. Salen sólo en el editor y **no** en el inbox: enseñarle al mesero unas plantillas
# que el dueño nunca aprobó es poner palabras en boca del negocio. Adoptarlas rellena el formulario
# y no guarda nada, así que el tenant sigue "sin configurar" hasta que pulsa guardar.
#
# Sin marcadores, por lo dicho arriba — y hay una prueba que comprueba que estas cuatro pasan su
# propia validación, porque una sugerida inválida es un botón que rompe la pantalla.
SUGGESTED_QUICK_REPLIES: tuple[QuickReply, ...] = (
    QuickReply(
        id="quick-on-the-way",
        name="Va en camino",
        text="¡Tu pedido ya salió! Llega en unos 20 minutos. 🛵",
    ),
    QuickReply(
        id="quick-payment-details",
        name="Datos para pagar",
        text="Puedes pagar por Nequi o Daviplata y mandarnos el comprobante por aquí. "
        "También recibimos efectivo y tarjeta al momento de la entrega. 💳",
    ),
    QuickReply(
        id="quick-thanks",
        name="Gracias",
        text="¡Gracias por tu compra! Nos alegra tenerte por aquí. 🙌",
    ),
    QuickReply(
        id="quick-one-moment",
        name="Un momento",
        text="¡Claro! Dame un momento y te confirmo. 🙏",
    ),
)
