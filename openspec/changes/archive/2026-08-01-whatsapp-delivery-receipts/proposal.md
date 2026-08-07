## Why

En el hilo de WhatsApp, un mensaje del equipo dice tres cosas: "Enviando…", nada, o que falló. El
"nada" es el 99% de los casos y significa **"lo aceptó el puente"**, que no es lo que el agente
quiere saber. Lo que quiere saber es si le llegó al cliente y si lo leyó, que es justo lo que su
teléfono personal le enseña con dos palomitas y él da por descontado.

La diferencia importa en el momento en que se usa esta pantalla. "Tu domicilio va en camino, sale
en 20 minutos" **entregado y leído** cierra el asunto. El mismo mensaje **sin entregar** significa
que el cliente tiene el teléfono apagado y que en veinte minutos va a haber un domiciliario en una
puerta que nadie abre. Hoy las dos cosas se ven exactamente igual, así que el agente llama por
teléfono a todo el mundo o no llama a nadie.

Esto estaba en el brief del inbox desde el principio y se quedó fuera por una razón concreta y ya
resuelta: **no escuchábamos `MESSAGES_UPDATE`**. El puente lo manda —está en su código, no es una
suposición— y nosotros nos suscribimos sólo a tres eventos.

## What Changes

- **Dos estados nuevos**, `delivered` y `read`, después de `sent`. `failed` sigue siendo el otro
  final y no entra en la escala.
- **Suscripción a `MESSAGES_UPDATE`** al emparejar, junto a los tres eventos que ya se registran.
  Queda **encendido por defecto** para todo número que se vincule a partir de ahora: el evento no
  es opcional ni configurable por tenant, es cómo funciona el canal.
- **Los números ya vinculados no reciben el evento hasta que se vuelva a registrar el webhook.**
  Volver a pulsar *Vincular* lo hace —`/webhook/set` es idempotente y no desconecta un número
  conectado—, y la pantalla de números lo dice.
- **Las transiciones son monótonas.** `pending → sent → delivered → read`, nunca hacia atrás. Es
  la regla que sostiene el change entero: los webhooks llegan desordenados, y un `DELIVERY_ACK`
  tardío detrás de un `READ` apagaría una palomita azul que el cliente ya se ganó.
- **Sólo los mensajes nuestros** (`fromMe: true`). El evento también viaja para los del cliente, y
  esos no llevan acuse: nadie enseña "leído" sobre el mensaje de otro.
- **Se emparejan por el id del proveedor** (`keyId` contra `provider_message_id`), que ya tiene
  índice único por tenant. Un id desconocido —un mensaje enviado desde el teléfono a mano, o uno
  anterior a este change— **se ignora en silencio** y responde 200.
- **`PLAYED` cuenta como leído.** Es lo que WhatsApp hace con un audio escuchado, y para el agente
  es la misma información.
- **Sin timbre de realtime.** El acuse viaja en el refresco que ya existe (10 s con la pestaña
  delante). Cada mensaje saliente produce dos o tres eventos más; tocar el timbre por cada uno
  triplicaría los refrescos del inbox entero para pintar una palomita.
- **En la burbuja**: ✓ enviado, ✓✓ entregado, ✓✓ en ember leído. Sólo en los mensajes del equipo.

## Capabilities

### Modified Capabilities

- `whatsapp-messaging`: el requisito de "los salientes se persisten y se reconcilian" se amplía
  con los dos estados nuevos, la monotonía y el emparejamiento por id; y el webhook gana un
  evento que atender antes de intentar leer el sobre como mensaje entrante.
- `frontend-whatsapp-inbox`: la burbuja de un mensaje del equipo enseña su acuse.

## Impact

- **Backend `messaging`**: `MESSAGE_DELIVERY_STATES` gana dos valores y —por fin— un uso: la
  función pura que ordena la escala y decide si una transición avanza. Normalizador
  `delivery_update(payload)` junto a `connection_update`, un caso de uso que aplica el acuse por
  `(tenant, provider_message_id)`, y el despacho en el webhook antes de `to_inbound`.
- **Sin migración.** `delivery_state` es `String(20)` sin CHECK ni enum, así que los valores
  nuevos entran sin tocar el esquema. Es la razón de que este change sea pequeño.
- **`bridge.start_pairing`**: un elemento más en `events`. Sin cambio de contrato.
- **Frontend**: `DeliveryState` gana dos valores, `MessageBubble` pinta el acuse, y la pantalla de
  números explica que un número vinculado antes de esto necesita volver a vincularse.
- **Sin permiso nuevo, sin endpoint nuevo, sin ajuste de tenant.**
- **Volumen de entrada**: sube, y es lo único que sube. Dos o tres `MESSAGES_UPDATE` por mensaje
  saliente, cada uno un `UPDATE` de una fila por id indexado, sin escrituras nuevas y sin timbre.
- **No rompe nada**: un mensaje que nunca reciba un acuse se queda en `sent`, que es exactamente
  lo que hoy significa y lo que hoy se pinta.

## Notes

Lo que este change **no** hace, dicho para que no se pida como bug:

- **No hay acuse de los mensajes del cliente hacia nosotros.** Marcar leído lo entrante es otra
  cosa (`/chat/markMessageAsRead`) y tiene consecuencia visible para el cliente: le apagaría el
  "no leído" en cuanto el mensaje entra en la bandeja, aunque nadie lo haya mirado. Sería mentir.
- **No se avisa de un mensaje sin entregar.** Un `sent` que lleva media hora sin `delivered` es
  información accionable —el teléfono está apagado— y podría ser una alerta. Pero eso es una regla
  del módulo de alertas con su umbral y su ventana, no una palomita, y merece su propio change.
