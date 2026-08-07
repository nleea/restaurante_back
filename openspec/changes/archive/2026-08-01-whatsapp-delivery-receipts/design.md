## Context

El canal ya persiste cada saliente antes de mandarlo (`pending`), guarda el id que devuelve el
puente y lo pasa a `sent` o `failed`. Lo que falta es todo lo que ocurre **después** del envío, y
no falta por diseño: falta porque el webhook se suscribe a tres eventos y el que cuenta no está.

Lo leído en el código del puente, que está en este repo (`evolution-api/`), no de memoria:

- `src/api/integrations/channel/whatsapp/whatsapp.baileys.service.ts` construye el sobre de
  `MESSAGES_UPDATE` como `{keyId, remoteJid, fromMe, participant, status, pollUpdates, instanceId}`
  —más `messageId` cuando encuentra el mensaje en su propia base— y lo manda para **cualquier**
  clave que no sea `status@broadcast`, incluidas las nuestras.
- `src/utils/renderStatus.ts` fija los valores de `status`: `ERROR`, `PENDING`, `SERVER_ACK`,
  `DELIVERY_ACK`, `READ`, `PLAYED`. Cuando el puente no sabe, manda `SERVER_ACK`.

Dos hechos del esquema actual hacen este change mucho más pequeño de lo que parece:

1. `delivery_state` es `String(20)` **sin CHECK y sin enum**, así que dos valores nuevos no tocan
   la base. `MESSAGE_DELIVERY_STATES` existe como tupla y hoy no la usa nadie.
2. Ya hay índice único `(tenant_id, provider_message_id)`, que es exactamente la clave por la que
   hay que buscar. No hace falta índice nuevo.

## Goals / Non-Goals

**Goals:**

- Que un mensaje del equipo diga si llegó al teléfono del cliente y si lo abrió.
- Que un acuse tardío no pueda apagar una palomita ya ganada.
- Que emparejar un número deje los acuses funcionando sin configurar nada más.
- Que un número ya vinculado tenga un camino claro —y dicho en la pantalla— para activarlos.

**Non-Goals:**

- **Marcar leído lo que entra.** Ver decisión 7.
- **Alertar de un mensaje sin entregar.** Es una regla de alertas con umbral y ventana, no una
  palomita. Ver `proposal.md` §Notes.
- **Acuse por sucursal, por tenant o configurable.** No es una preferencia: es cómo funciona el
  canal. Un interruptor aquí sólo serviría para que alguien lo apagara y luego reportara que las
  palomitas no salen.
- **Histórico de acuses** (cuándo se entregó, cuándo se leyó). Se guarda el estado, no la línea de
  tiempo: un `delivered_at` sólo se justifica el día que exista la alerta de "sin entregar".
- **Reconciliar mensajes viejos.** Los anteriores al change se quedan en `sent` para siempre, que
  es la verdad de lo que sabemos de ellos.

## Decisions

### 1. La escala, y que sólo avanza

```
pending (0) → sent (1) → delivered (2) → read (3)          failed: fuera de la escala
```

Una función pura decide: `advance(current, incoming)` devuelve el nuevo estado sólo si el rango
sube, y el mismo si no. Toda la lógica del change cabe ahí y se prueba sin base de datos.

**Por qué es lo primero del diseño y no un detalle:** los webhooks llegan desordenados, y en
WhatsApp llegan casi siempre dos seguidos (`DELIVERY_ACK` y `READ`) con milisegundos de diferencia.
Aplicarlos a pelo hace que una palomita azul parpadee a gris según el orden en que el puente
resuelva sus reintentos. Un acuse que retrocede es peor que ningún acuse: el agente ve "no leído"
sobre algo que sí se leyó y llama al cliente.

`failed` fuera de la escala y no en el 0: un envío fallido **no tiene id de proveedor** —el puente
nunca lo aceptó—, así que ningún acuse puede emparejar con él. La regla es una red por si algún día
se marca `failed` un mensaje que sí llegó a salir.

`ERROR` del puente **no** se traduce a `failed`. `failed` significa "no lo pudimos entregar al
puente", que es lo que dice la spec vigente y lo que el agente puede accionar reenviándolo; un
`ERROR` posterior es otra cosa y no se sabe qué, así que se ignora.

### 2. `PLAYED` es `read`

WhatsApp lo usa para el audio escuchado. Un tercer estado para eso sería una palomita más que
explicar a cambio de una distinción que a un agente de restaurante no le cambia ninguna decisión.

### 3. `SERVER_ACK` es `sent`, y por eso casi nunca hace nada

El puente manda `SERVER_ACK` también como valor por defecto cuando no sabe el estado. Traducirlo a
`sent` lo vuelve inofensivo: el mensaje ya está en `sent`, la transición no sube y no pasa nada.
Es exactamente el comportamiento que se quiere de un "no sé".

### 4. Emparejar por `keyId`, y el desconocido en silencio

`keyId` contra `provider_message_id`, dentro del tenant de la instancia. Un `UPDATE` por clave
indexada, sin lectura previa.

**El id desconocido tiene que ser silencio y 200**, no un error ni un log de warning por cada uno:
el puente reporta también los mensajes que el dueño escribe desde su propio teléfono, y ésos no
están en nuestra base ni deben estarlo. Un warning por cada uno convierte el log en ruido el primer
día que alguien conteste desde el móvil.

### 5. Se despacha antes de `to_inbound`

Igual que `connection_update`. Hoy `_evolution_inbound` ya devolvería `None` para un
`messages.update` —filtra por `event != "messages.upsert"`—, así que el orden es defensa en
profundidad y no una corrección. Pero el orden correcto es el que hace que la respuesta diga la
verdad: `{"status": "receipt"}` en vez de `"payload sin id o remitente"`, que es lo que se lee
cuando alguien depura el webhook a las once de la noche.

### 6. Sin timbre de realtime

El acuse no toca `INBOX_TOPIC`. Viaja en el refresco que ya existe: `POLL_FULL_MS = 10 s` con la
pestaña delante, más cualquier timbre que suene por otra razón.

**Por qué:** un timbre provoca que **todos** los clientes del inbox reconsulten la lista y el hilo
abierto. Cada mensaje saliente genera dos o tres `MESSAGES_UPDATE`. Tocar el timbre por cada uno
multiplica por tres los refrescos del inbox entero de un restaurante en hora punta para pintar una
palomita que el agente va a ver de todas formas en diez segundos. La relación coste/beneficio no
está ni cerca.

Si algún día se quiere instantáneo, la salida no es tocar el timbre general: es un topic propio por
conversación al que sólo esté suscrito quien tiene ese hilo abierto.

### 7. No se marca leído lo que entra

Existe (`/chat/markMessageAsRead`) y sería fácil. No se hace porque **tiene consecuencia visible
para el cliente**: le apagaría el "no leído" en cuanto el mensaje entra en nuestra bandeja, aunque
no lo haya mirado nadie. Es decirle al cliente que le leímos cuando no le leímos, y es peor que no
decirle nada. El día que se haga, tiene que colgar de que una persona ABRA el hilo, no de que el
mensaje llegue.

### 8. El número ya vinculado: volver a vincular, y decirlo

`POST /webhook/set/{instance}` es idempotente y no toca la conexión, así que `start_pairing` sobre
un número conectado re-registra los eventos y devuelve `None` en vez de un QR —ya está conectado,
no hay nada que escanear—. Es el camino que ya existe y no hace falta endpoint nuevo.

Lo que sí hace falta es **decirlo en la pantalla de números**, porque el síntoma sin explicación
—"a mis compañeros les salen las palomitas y a mí no"— es indistinguible de un fallo.

### 9. La burbuja: ✓, ✓✓, ✓✓ ember

Sólo en `sender_type === 'employee'`. Un carácter y un color, con `aria-label` que lo dice en
palabras: el color no puede ser la única diferencia entre entregado y leído.

El leído usa **ember**, el acento de la casa, y no el azul de WhatsApp. Copiar el azul de WhatsApp
dentro de una pantalla de "El Pase" es meter la marca de otro en la nuestra por una asociación que
el ✓✓ ya lleva encima.

## Risks / Trade-offs

- **El acuse tarda hasta 10 s en pintarse →** aceptado a cambio de no triplicar el tráfico del
  inbox (decisión 6). Con el hilo abierto y la pestaña delante, 10 s.
- **Los números ya vinculados no reportan hasta que alguien los revincule →** se dice en la
  pantalla de números (decisión 8). No se fuerza una revinculación automática al desplegar: tocar
  la conexión de un número que está funcionando, sin que nadie lo pida, es el peor cambio posible
  en este módulo.
- **Sube el tráfico entrante del webhook (×2–3 por saliente) →** cada uno es un `UPDATE` por clave
  única indexada, sin inserciones y sin timbre. Si algún día molesta, la salida es descartar
  `SERVER_ACK` en el borde, que es el que más se repite y el que nunca cambia nada.
- **Un mensaje entregado y luego borrado por el cliente sigue diciendo "entregado" →** cierto y
  correcto: lo que se afirma es que llegó, no que siga ahí.
- **El puente puede dejar de mandar el evento y no nos enteraríamos** (los mensajes se quedarían en
  `sent`, que es lo de hoy). Degrada al comportamiento actual en vez de romperse, que es la forma
  correcta de fallar aquí.

## Migration Plan

1. **Sin migración de base de datos**: `delivery_state` no tiene CHECK ni enum. Los valores nuevos
   sólo existen en código.
2. Backend y frontend son aditivos; se despliegan juntos sin ventana.
3. Los números ya vinculados empiezan a reportar cuando alguien pulse *Vincular* otra vez. Es
   manual a propósito.
4. **Rollback**: revertir el código deja filas con `delivered`/`read` que el front antiguo no sabe
   pintar. Se comportan como "ni pendiente ni fallido", que es exactamente el hueco donde ya caía
   `sent`. No hay que limpiar nada.

## Open Questions

Ninguna.
