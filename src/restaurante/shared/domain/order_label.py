"""Cómo se llama un pedido cuando hay que decirlo en voz alta.

Las comandas **no llevan columna de código**: la etiqueta corta se deriva del id. Eso está bien —un
contador por tenant sería una fila más que bloquear en cada pedido— pero obliga a que la derivación
sea UNA, porque el número que el cliente lee en su WhatsApp tiene que ser el mismo que el
mostrador dice en voz alta y el mismo que sale impreso en el tiquete.

Vivía duplicada en tres sitios (domicilios, mensajería y el storefront), y el tercero se había
desviado: devolvía el UUID entero. El cliente veía `C328A1B2` en su chat y
`c328a1b2-4f5e-...` en la pantalla de confirmación, para el mismo pedido.

Ocho caracteres hexadecimales son 4.300 millones de combinaciones: de sobra para que dos pedidos
vivos de un mismo negocio no colisionen, y cortos para leerlos por teléfono. **No es un
identificador** —para eso está el uuid— sino una etiqueta para humanos.
"""

from __future__ import annotations

import uuid


def order_label(order_id: uuid.UUID) -> str:
    """`C328A1B2`. La misma etiqueta en el chat, en el mostrador y en el tiquete."""
    return order_id.hex[:8].upper()
