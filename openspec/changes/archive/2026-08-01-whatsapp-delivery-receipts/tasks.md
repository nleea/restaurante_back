> Lee `design.md` antes de empezar. El change es **una escala que sólo sube** (grupo 1) y un
> evento al que suscribirse (grupo 4). Todo lo demás es fontanería. Si al terminar un
> `DELIVERY_ACK` tardío puede apagar un `read`, el change ha fallado por mucho que las palomitas
> salgan en la pantalla.
>
> **No hay migración**: `delivery_state` es `String(20)` sin CHECK ni enum. Si acabas escribiendo
> una, párate y relee la decisión — probablemente le estés poniendo una constraint a una columna
> que lleva viva desde la fase 1 y eso es otro change.
>
> Orden: 1 → 2 → 3 → 4 (backend completo y probado) → 5 → 6. El 7 al final.

## 1. Backend — la escala, como funciones puras

> En `messaging/domain/delivery.py`, sin base, sin red y sin reloj. Se prueba en
> `tests/modules/messaging/test_delivery_receipts.py` **sin levantar la app**, y esa suite es la
> que sostiene el change.

- [x] 1.1 Añadir `delivered` y `read` a `MESSAGE_DELIVERY_STATES`, y darle por fin un uso a esa
      tupla en vez de dejarla de adorno
- [x] 1.2 `DELIVERY_RANK`: `pending` 0, `sent` 1, `delivered` 2, `read` 3. `failed` **no está en el
      mapa** — es el otro final, no un escalón (design §1)
- [x] 1.3 `advance(current, incoming)`: devuelve el estado nuevo sólo si el rango sube; si no,
      devuelve `current` intacto. Un `current` fuera de la escala (`failed`) devuelve `current`
- [x] 1.4 `state_from_provider(status)`: `DELIVERY_ACK`→`delivered`, `READ`/`PLAYED`→`read`,
      `SERVER_ACK`/`PENDING`→`sent`, `ERROR`→**None** (no es nuestro `failed`, design §1).
      Desconocido → `None`
- [x] 1.5 Pruebas de la monotonía, que es el change: `read` + `delivered` tardío sigue `read`; el
      mismo acuse dos veces no cambia nada; `sent` + `read` sin pasar por `delivered` sí sube;
      `failed` + cualquier cosa sigue `failed`
- [x] 1.6 Prueba de que `SERVER_ACK` sobre un `sent` es un no-op — es el valor por defecto del
      puente cuando no sabe, y tiene que ser inofensivo

## 2. Backend — normalizar el sobre

- [x] 2.1 `DeliveryReport` (id del proveedor + estado ya traducido) y `delivery_update(payload)` en
      `api/schemas.py`, al lado de `connection_update` y con la misma forma: `None` si el sobre no
      es esto
- [x] 2.2 Leer `data.keyId` (y `data.messageId` como alternativa: el puente lo manda cuando
      encuentra el mensaje en su propia base). Sin id → `None`
- [x] 2.3 **Sólo `fromMe: true`.** El evento viaja igual para los mensajes del cliente y ésos no
      llevan acuse. Es una de las trampas ya conocidas del canal
- [x] 2.4 Pruebas con el sobre REAL de Evolution v2.3.7 —`{keyId, remoteJid, fromMe, status,
      instanceId}`, tal y como lo construye `whatsapp.baileys.service.ts`—, no con uno inventado

## 3. Backend — aplicar el acuse

- [x] 3.1 Método de repositorio que busca por `(tenant_id, provider_message_id)` —índice único que
      YA existe, no hace falta uno nuevo— y aplica `advance`. Devuelve si cambió algo
- [x] 3.2 Sólo sobre mensajes salientes (`sender_type == 'employee'`): un acuse no puede tocar un
      mensaje del cliente ni aunque el id coincidiera
- [x] 3.3 Caso de uso en el servicio: resuelve el tenant por la instancia y delega. Instancia
      desconocida → ignorado, nunca excepción
- [x] 3.4 Despacho en el webhook **antes de `to_inbound`**, como `connection_update`, devolviendo
      un `WebhookAck` que diga que fue un acuse (design §5)
- [x] 3.5 Id desconocido → 200 en silencio y **sin warning por cada uno**: el puente reporta también
      lo que el dueño escribe desde su propio teléfono, y un log por mensaje sería ruido puro
- [x] 3.6 Pruebas de API: el acuse sube el estado; no crea mensajes ni toca el estado de la
      conversación; un id de otro tenant no se alcanza; un `messages.update` no acaba nunca en el
      hilo como mensaje del cliente

## 4. Backend — suscribirse al evento

- [x] 4.1 `MESSAGES_UPDATE` en la lista de `events` de `start_pairing`. Es el change entero desde
      fuera: sin esto, nada de lo anterior recibe un solo sobre
- [x] 4.2 Prueba de que emparejar registra los cuatro eventos, para que nadie los recorte luego
      "porque sobran"

## 5. Frontend — la burbuja

- [x] 5.1 `DeliveryState` gana `'delivered'` y `'read'` en el contrato
- [x] 5.2 Acuse en `MessageBubble`, **sólo** en `sender_type === 'employee'`: ✓ enviado, ✓✓
      entregado, ✓✓ en ember leído. Nada en los del cliente
- [x] 5.3 `aria-label` que dice el estado en palabras: el color no puede ser la única diferencia
      entre entregado y leído (lectores de pantalla, y una pantalla al sol)
- [x] 5.4 Ember y **no el azul de WhatsApp**: es la paleta de la casa, no la de otro
- [x] 5.5 Pruebas: los cuatro estados se distinguen, el entrante no lleva acuse, `failed` sigue
      siendo inconfundible

## 6. Frontend — la pantalla de números

- [x] 6.1 Decir que un número vinculado antes de esto **no reporta hasta volver a vincularlo**, y
      que volver a vincular **no desconecta** un número conectado. Sin esto, el síntoma ("a mis
      compañeros les salen las palomitas y a mí no") es indistinguible de un fallo
- [x] 6.2 Prueba de que el aviso está

## 7. Cierre

- [x] 7.1 `docs/messaging/BRIDGE.md`: el evento nuevo en la tabla, el sobre de `MESSAGES_UPDATE`
      con sus valores de `status`, y la nota de la revinculación
- [x] 7.2 Puertas verdes: `ruff`, `mypy`, suite de backend, `vitest`, `type-check` y `eslint`
- [ ] 7.3 Comprobar a mano contra el número real: mandar una respuesta, verla pasar a ✓✓ y a leído
