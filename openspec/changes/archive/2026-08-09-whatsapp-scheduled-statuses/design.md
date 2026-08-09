## Context

Este change mete en el módulo la primera emisión que **no es una respuesta**, y lo hace en un canal
cuya regla número uno es no escribir primero. Toda la tensión del diseño sale de ahí: la mecánica es
sencilla —un cron, un POST, una tabla de constancia— y lo difícil es *a quién*, *cuántos* y *qué
podemos afirmar después*.

Lo que ya existe, y en lo que esto se apoya sin construir nada nuevo:

- **`try_claim_emission` + índice único parcial** sobre `whatsapp_outbound_emissions`, con dos clases
  de clave conviviendo en una columna de texto (`greeting:<conv>`, `status:<pedido>:<estado>`). El
  docstring del modelo documenta *por qué* la clave es una cadena y no una tupla de columnas: en SQL
  dos `NULL` no son iguales, así que la tupla es única consigo misma y el aviso sale en cada rebote.
  Una tercera clase encaja sin inventar mecanismo.
- **`business/domain/hours.py`**: la semana como conjunto de ventanas, `weekday` 0=lunes…6=domingo,
  minutos desde medianoche, hora **local naive**, y todo el cálculo en funciones puras. Es el
  precedente exacto de un horario en este repo, y es el que se copia.
- **`business/application/clock.py`**: cualquier cosa que se compare con una hora del negocio pasa
  por ahí. Su docstring cuenta el fallo que lo hizo nacer, y es *este mismo* fallo: a partir de las
  7pm en Colombia, UTC cruza la medianoche y **el día de la semana se corre**.
- **`list_contactable(tenant, branch)`** (`repositories.py:336`): los contactos que escribieron a esa
  sede, ordenados por `max(sent_at) desc`. Ya es casi literalmente la consulta de audiencia.
- **`BridgeWhatsAppGateway`** con un verbo por método y todo lo específico del puente confinado en un
  fichero, detrás de `GuardedWhatsAppGateway`, que es lo único que la raíz de composición inyecta.
- **El worker de alertas**, que ya importa el bridge, el guard y los repositorios de `messaging`
  (`whatsapp_escalation.py:39-49`), ya tiene cola propia (`arq:queue:alerts`) y ya declara que se
  ejecuta exactamente una vez.
- **`media_store.py`**: subir a R2 firmando un PUT contra nosotros mismos, clave con tenant, URL
  pública y opaca. Mismo trato que el comprobante de pago y el multimedia entrante.

Y el terreno ajeno, leído del código de Evolution y no de memoria:

| Hecho | Dónde |
|---|---|
| `POST /message/sendStatus/{instance}`, cabecera `apikey` | `sendMessage.router.ts:101` |
| `type: text\|image\|video\|audio`; `text` exige `backgroundColor` **y** `font` | `whatsapp.baileys.service.ts:2690` |
| Obliga a `statusJidList` **o** `allContacts: true` | `whatsapp.baileys.service.ts:2685` |
| `allContacts` lee la tabla `contact` **de Evolution**, no la nuestra | `whatsapp.baileys.service.ts:2678` |
| Parte en lotes de 10 y reenvía con el **mismo `messageId`** (una sola historia) | `whatsapp.baileys.service.ts:2224-2272` |
| Los lotes van en `Promise.allSettled` y devuelve sólo el primero | `whatsapp.baileys.service.ts:2262` |
| `// TODO: Revisar funcionamento do envio de Status` | `sendMessage.router.ts:100` |

## Goals / Non-Goals

**Goals**

- Que el menú del día salga a las once sin que nadie toque el teléfono del negocio.
- Que la audiencia sea **explicable en una frase** al dueño, y que él pueda verla contada antes de
  publicar.
- Que instalar el change no cambie el comportamiento de ningún tenant hasta que cree un estado.
- Que ninguna reducción de la audiencia —`@lid`, opt-out, 90 días, tope— ocurra en silencio.
- Que un reinicio del worker no pueda provocar una tanda de publicaciones atrasadas.
- Que un guardado inocuo no pueda provocar un reenvío.

**Non-Goals**

- Saber cuántas personas vieron el estado. No hay forma (decisión 10).
- `allContacts: true`. Es la tabla de Evolution, de tamaño desconocido, sin nuestro opt-out y sin
  nuestra ventana de inactividad: es exactamente el botón que quema el número.
- Estados de vídeo y audio. El endpoint los acepta; el compositor de v1 hace texto e imagen.
- Segmentar la audiencia (por barrio, por gasto, por lo que sea). La audiencia es una sola lista con
  reglas fijas; segmentar es un change propio y necesita antes que esto funcione.
- Responder a quien contesta un estado. Una respuesta a un estado llega como un mensaje normal y la
  bandeja ya lo atiende; no hay hilo especial que construir.
- Publicación manual "ahora mismo" sin franja. Cabe después y es trivial; se deja fuera para que la
  única vía de emisión sea la programada y el cron sea el único camino que hay que probar.

## Decisiones

### 1. La audiencia es de la SEDE, no del negocio

`is_reachable` es deliberadamente **no** por sede, y su docstring lo justifica: *"escribirle a
cualquier sucursal te hace contactable por el negocio"*. Para un mensaje directo es correcto. Para un
estado es **falso**, y el modelo ya contiene la asimetría:

```
whatsapp_sessions       BranchScoped    ← el estado se publica DESDE un número concreto
whatsapp_conversations  BranchScoped    ← el hilo es de una sede
whatsapp_contacts       TenantScoped    ← la persona es del negocio
```

Quien escribió al número de la sede A no tiene guardado el número de la sede B: su teléfono no
enseña esa historia, pase lo que pase. Así que la audiencia se construye sobre
`whatsapp_conversations.branch_id`, igual que `list_contactable`, y no sobre `is_reachable`.

"Escribieron ellos primero" se hereda de esa misma consulta. Técnicamente un estado no lo necesita
—no hay ventana de 24h ni política que cumplir—, pero es el mejor indicio disponible de "esta
persona probablemente nos tiene guardados", y es una consulta que ya existe y ya está probada.

### 2. Los `@lid` fuera, y contados

`shared/domain/phones.py:35` es explícito: un JID de privacidad se devuelve **intacto** porque *"no
es un teléfono, es lo único con lo que se le puede escribir a ese contacto"*. Y
`list_contactable` lo repite: *"puede ser un número o un `@lid`. A efectos de enviar da igual"*.

Para un mensaje directo da igual. Para `statusJidList` es un desconocido, y el modo de fallo es el
peor posible:

```
@lid en el lote  →  Baileys lo rechaza  →  Promise.allSettled se lo come
                 →  Evolution devuelve 201  →  "publicado ✓"  →  nadie lo recibió
```

Un fallo que se presenta como éxito es peor que un fallo. Así que se excluyen y **se cuentan
aparte**: la pantalla dice *"12 contactos sin número visible — no reciben estados"*. Excluir a
alguien de forma visible siempre gana a incluirlo y fallar callado.

**Comprobado el 2026-08-09 contra la instancia real: un `@lid` en `statusJidList` NO recibe el
estado.** La hipótesis segura era la verdadera, así que el filtro se queda y el contador "sin número
visible" describe algo real. Queda anotado porque el diseño se escribió *sin* saberlo —con la
exclusión por prudencia, no por certeza— y quien lea esto dentro de un año merece saber cuál de las
dos cosas era.

Si algún día cambiara (Baileys evoluciona), lo que hay que tocar es exactamente un `continue` en
`resolve_audience` y el contador se queda en cero solo.

Los JIDs bien formados se construyen añadiendo `@s.whatsapp.net` a los dígitos. Sí, es reconstruir
un JID, que fue una de las trampas conocidas del canal — pero aquí no hay alternativa:
`provider_remote_jid` se guarda por **mensaje**, no por contacto, y la audiencia son contactos.

### 3. El tope es la red; los 90 días son el criterio

Cuatro reducciones, en este orden, y todas visibles:

```
list_contactable(tenant, branch)          340
  − JID de privacidad (@lid)             − 12   → "sin número visible"
  − opt-out                              −  4   → "pidieron no recibir"
  − sin escribir en 90 días              −118   → "inactivos"
  ────────────────────────────────────    206
  tope (settings, con techo)        →     200   → "se omiten 6"
                                           │
                                    20 lotes de 10  →  20 envíos
```

La ventana de 90 días vale más que el tope, y por eso va primero en el razonamiento aunque el tope
sea el que da miedo. Quien escribió una vez hace ocho meses casi seguro borró el chat: es volumen de
salida —el que hace que WhatsApp mire un número— sin audiencia real detrás. Recortar por inactividad
quita riesgo sin quitar espectadores. El tope, en cambio, sí quita espectadores, y por eso es lo
último que muerde y lo único que se anuncia como *omitido*.

El tope **no es una constante en el código**: va en settings, como el resto de `WHATSAPP_*`, con un
techo absoluto por encima que el ajuste no puede superar. El número correcto sólo se conoce viendo
si el número aguanta, y una constante obligaría a un despliegue para averiguarlo.

Jitter entre lotes, por lo mismo. Veinte POST idénticos seguidos son una firma; veinte con pausa
irregular, no tanto.

### 4. Opt-out: una columna, no una tabla

`whatsapp_contacts.status_opt_out: bool` con default `false`.

Una tabla `whatsapp_status_optouts` sería más "correcta" y no compra nada: no hay metadatos que
guardar (¿cuándo? ¿quién? nadie los va a mirar), no hay más de un tipo de opt-out que distinguir, y
la consulta de audiencia pasaría de un `WHERE` a un `LEFT JOIN ... IS NULL` que es más fácil de
escribir mal.

Va en `whatsapp_contacts` y no en `whatsapp_conversations` **a propósito**, aunque la audiencia sea
por sede: "no me manden más" es una petición de la persona al negocio, no a una sede. Que se lo
tengan que pedir a cada sucursal por separado sería exactamente la clase de detalle que hace que la
gente bloquee el número en vez de volver a pedirlo.

El interruptor vive en la bandeja, en la ficha del contacto, con `messaging.attend` — el permiso que
ya tiene quien lee los chats. Quien pide no recibir más lo pide *en el chat*, y quien lo lee es quien
atiende; poner el interruptor en la pantalla de estados obligaría a cambiar de pantalla y de permiso
para cumplir una petición que acabas de leer.

### 5. El horario son filas, y una franja es un día O una fecha

```sql
whatsapp_status_slots (
  status_id,
  weekday   int  NULL,   -- 0=lunes … 6=domingo
  on_date   date NULL,   -- fecha concreta
  minute    int  NOT NULL, -- desde medianoche, hora LOCAL
  CHECK ( (weekday IS NULL) <> (on_date IS NULL) )  -- exactamente uno
)
```

Copia directa de `operating_hours`, con una sola adición: `on_date`. Y esa adición es la que hace que
**no exista un campo `kind`**. Con el CHECK, una franja se explica sola:

| lo que quiere el dueño | filas |
|---|---|
| todos los días a las 11:00 | 7 filas `weekday=0..6, minute=660` |
| viernes y sábado a las 18:30 | 2 filas `weekday=4,5, minute=1110` |
| el 15 de agosto a las 18:00 | 1 fila `on_date=2026-08-15, minute=1080` |

Un `kind: once | weekly` en la cabecera sería un **segundo sitio donde se decide el mismo hecho**, y
podría contradecir a sus propias filas (`kind='once'` con siete filas de `weekday`: ¿quién gana?).
Es el mismo argumento por el que no hay bandera de horario de atención (decisión 7), aplicado dos
veces en el mismo change.

Consecuencia bonita y gratis: **un estado de fecha pasada se vuelve inerte solo**. La consulta sólo
mira lo que vence *hoy*, así que no hace falta ninguna máquina de estados que lo apague después de
publicar.

Nada de cadenas de cron. `0 11 * * 1,3,5` es potente y es indecible para el dueño de un restaurante,
y el repo ya eligió el otro camino dos veces.

Cómo se guarda: **borrar todo e reinsertar**, como `operating_hours` (`repositories.py:13` importa
`sql_delete`). Es lo correcto para un conjunto que se edita como un todo — y es justamente lo que
obliga a la decisión siguiente.

### 6. La clave de emisión va sobre el reloj de pared, no sobre el id de la franja

Esta es la decisión menos obvia del change.

Si la clave llevara el `slot_id`, el borrar-y-reinsertar de la decisión 5 le da UUIDs nuevos a las
franjas en **cada guardado**:

```
11:00  se publica  →  emisión "status:<id>:<slot_A>:2026-08-09"
11:05  el dueño corrige una tilde del texto y guarda
       → franjas borradas y reinsertadas → slot_A ya no existe, ahora es slot_Z
11:06  el cron busca "status:<id>:<slot_Z>:2026-08-09"  →  no hay
       →  vuelve a publicar          💥
```

Un guardado inocuo dispara el reenvío, y el dueño no tiene forma de relacionar una cosa con la otra.
La clave, entonces:

```
status:<status_id>:<fecha_local>:<minuto>       →  "status:8f3a…:2026-08-09:660"
```

Sobrevive a la reescritura de filas, es legible en la base sin un solo join, y usa el **mismo formato
para franjas semanales y de fecha concreta** — la fecha local ya es el discriminante, así que no hay
dos formatos que mantener.

Efecto secundario, y sostengo que es el correcto: mover 11:00 → 11:30 el mismo día **sí** vuelve a
publicar. Cambiaste la hora; querías que saliera a la nueva hora. Y quitar una franja no puede
resucitar nada, porque lo que no existe no vence.

Riesgo residual, aceptado: mover una franja *hacia atrás* dentro del mismo día (11:00 ya publicado →
10:30) publica otra vez, porque 10:30 también está vencido. Es raro, es visible en el registro de
publicaciones, y el estado anterior sigue vivo las 24h — así que el peor caso es dos historias del
mismo día, no una pérdida.

### 7. Sin bandera de "sólo si estamos abiertos"

El caso: "menú del día, todos los días a las 11:00" en una sede que cierra los lunes.

| | lunes | modo de sorpresa |
|---|---|---|
| respetar el horario | no sale | **silencio inexplicable** — el dueño no sabe por qué |
| no respetarlo | sale | anuncio con el local cerrado — ridículo, pero **visible** |

Se elige no respetarlo, y **sin bandera**. El selector de días de la semana ya es la respuesta: el
dueño desmarca el lunes, y eso es una sola verdad en un solo sitio. Una `only_when_open` sería el
segundo sitio, y sería el que gana en silencio.

Es la excepción deliberada a la regla del asistente —*cerrado silencia al bot*— y por el mismo motivo
que las FAQs contestan cerradas: un estado **no promete atención**. Es un cartel, no una
conversación. Un cartel que dice "mañana hay sancocho" el día que estás cerrado es válido.

### 8. Corre en el worker de alertas

Tres razones, en orden de peso:

1. **Ya habla WhatsApp.** `whatsapp_escalation.py:39-49` importa los modelos, los repositorios, el
   bridge y el guard de `messaging`. No se abre ninguna dirección de acoplamiento nueva.
2. **Su invariante es la que hace falta.** Su docstring grita *"EJECUTA EXACTAMENTE UNO"* y explica
   que `unique=True` en el cron evita el solape dentro de un proceso y no puede evitarlo entre dos.
   Un programador de tareas necesita exactamente esa garantía, y aquí ya está escrita y desplegada.
3. **Un worker nuevo cuesta de verdad.** Tercera cola, tercer Deployment, y el tercer par
   `manual-config` / `manual-secret` en k8s — que ya se olvidó dos veces y costó dos commits de
   arreglo. Todo eso para **un cron**.

El precio, dicho de frente: el worker deja de tener una sola responsabilidad, y su docstring —que hoy
es un texto muy bueno sobre vigilancia— pasa a describir dos cosas. Hay que reescribirlo, no
ampliarlo con un párrafo pegado al final, y la razón del "exactamente uno" pasa a ser doble: evitar
trabajo duplicado en las alertas y evitar **publicaciones duplicadas** en los estados. La segunda es
más grave que la primera, y eso conviene que quede escrito donde alguien lo lea antes de escalar el
Deployment a dos réplicas.

Sobre las colas: los estados usan la de alertas, que ya existe. Es justamente el fallo que documenta
`ALERTS_QUEUE` —un worker sacando un job cuya función no conoce, escribiendo `function not found` y
tirándolo— y aquí no puede pasar porque es el mismo proceso el que declara el cron y lo ejecuta.

### 9. La ventana de gracia, y `skipped_late` como fila

Un cron por minuto (`unique=True`) que resuelve, todo en hora local vía `clock.py`:

```
now_local()                      ← NUNCA datetime.now(UTC): a partir de las 7pm en
  │                                Colombia el DÍA DE LA SEMANA se corre, y publicarías
  │                                el estado de mañana. Es el fallo que hizo nacer clock.py.
  ├─ franjas vencidas hoy: (weekday == hoy OR on_date == hoy) AND minute <= ahora
  ├─ sin emisión para status:<id>:<fecha>:<minuto>
  │
  ├─ ¿ahora − vencimiento > grace?
  │     SÍ  →  publication(state='skipped_late')  ·  no publica  ·  reclama la emisión
  │     NO  →  audiencia → lotes de 10 con jitter → publication('published' | 'failed')
  │
  └─ el barrido es autoritativo: es lo único que hay
```

**La gracia son 30 minutos**, y existe porque el estado caduca a las 24 horas: si el worker estuvo
caído desde las once, sacar el menú del día a las tres de la tarde es peor que no sacarlo. Sin
gracia, un reinicio de lunes por la mañana vomita de golpe todas las franjas atrasadas del día.

Lo que hace defendible el "no publicar" es que **deja fila**. `skipped_late` es una publicación con
su hora y su motivo, no un silencio: el dueño abre la pantalla, ve "10:00 · omitido, fuera de la
ventana" y sabe qué pasó. Y reclama la emisión igual, para que el barrido del minuto siguiente no lo
reconsidere eternamente.

### 10. Qué podemos afirmar, y qué no

Tres muros, y ninguno es nuestro:

1. **No hay vistas.** Evolution no devuelve espectadores de un estado, y los `MESSAGES_UPDATE` de
   los acuses ✓✓ son de mensajes, no de estados. Nunca vamos a poder decir "lo vieron N".
2. **Un estado sólo lo ve quien te tiene guardado.** Es cosa del teléfono del receptor y de sus
   ajustes de privacidad, invisible desde aquí. Todas nuestras defensas —"escribieron primero", 90
   días— son *indicios* de eso, nunca certezas.
3. **El fallo parcial es invisible.** `Promise.allSettled` en el lote 7 de 20 y Evolution devuelve
   201 con el mensaje del lote 1. No sabemos cuántos lotes entraron.

Así que el vocabulario de la UI se elige a partir de eso, y se elige a propósito:

| decimos | significa exactamente |
|---|---|
| **publicado** | el puente aceptó la publicación |
| **enviado a 200** | 200 JIDs iban en la petición |
| ~~visto por~~ | nunca |
| ~~entregado a~~ | nunca |

`recipient_count` es *a cuántos se dirigió*, y el nombre de la columna debería decirlo para que nadie
lo lea como "a cuántos llegó". Y `provider_message_id` se guarda —es el id de la primera tanda— por
lo mismo que se guarda en los mensajes: es lo único con lo que se puede correlacionar algo después.

### 11. La composición: el texto es una tarjeta, la imagen es una URL

`type: 'text'` exige `backgroundColor` y `font` o es un 400. Consecuencias de diseño:

- El dominio guarda `bg_color` y `font` **no nulos** para los estados de texto, con valores por
  defecto sensatos. Descubrir el 400 al publicar —a las once, en el worker, sin nadie mirando— es el
  peor momento posible. Se valida **al guardar**, que es el criterio que ya usan los marcadores de
  las plantillas (`templates.py`) y que ya está justificado allí.
- La vista previa **es** la tarjeta: color de fondo real y fuente real. No hay margen para que la
  previsualización engañe, porque los dos parámetros que la definen son los dos que se envían.
- La imagen va a R2 con `presign_put` y a Evolution le llega una **URL**, no base64. El endpoint
  acepta multipart, pero un base64 de una foto atravesando nuestro worker y su cliente httpx es
  memoria y latencia por nada, cuando ya existe el camino presignado y ya guarda con clave por
  tenant. `caption` es el pie.
- La misma opacidad-por-URL que el comprobante y el multimedia entrante. Con una diferencia que
  conviene notar y que juega a favor: esta imagen **se publica a propósito**, así que es la menos
  sensible de las tres.

## Riesgos / Trade-offs

- **La cuenta de WhatsApp.** Es el riesgo real y no se elimina, se acota: 90 días, tope bajo con
  techo, jitter, opt-out. Si el número cae, cae el canal entero —bandeja, avisos de pedido,
  asistente—, no sólo esta feature. De ahí que el tope arranque bajo y se suba mirando.
- **`@lid`**: si resulta que sí funciona, estamos excluyendo gente sin necesidad. Es visible en la
  pantalla y se arregla borrando un filtro. El error contrario no se arregla: no se ve.
- **El worker con dos trabajos.** Se paga en claridad, y se paga a cambio de no añadir un tercer
  Deployment por un cron. Si algún día los estados crecen —segmentación, más volumen, reintentos—,
  extraerlos a su propio worker es un change limpio, no un rescate.
- **Mover una franja hacia atrás el mismo día republica** (decisión 6). Aceptado: visible, y el peor
  caso son dos historias que caducan solas.
- **La truncación es una decisión que el sistema toma por el dueño.** Se mitiga haciéndola ruidosa en
  los dos sitios —antes de publicar y en el registro—, no ocultándola.
- **Nadie sabrá si funcionó de verdad** más allá de "el puente dijo sí". El primer estado real hay
  que mirarlo en un teléfono. Es una prueba manual, no automatizable, y conviene que esté escrita en
  `tasks.md` como tal y no darla por hecha.

## Migration Plan

- **0047**: tres tablas nuevas + `whatsapp_contacts.status_opt_out` con default `false`.
- **Nadie estrena comportamiento.** Sin estados creados, el cron consulta, no encuentra nada y
  termina. Esto es distinto del change de las FAQs, donde los tenants existentes despertaban con
  cuatro respuestas sembradas y hubo que decidir si nacían encendidas: aquí el conjunto vacío es el
  estado inicial natural y no hay nada que sembrar.
- **Sin `scripts.seed`**: `messaging.manage` ya está en el catálogo y ya gatea el editor de
  autorespuestas. Un permiso nuevo sí lo habría exigido, y es el fallo que deja a la pantalla nueva
  en 403 para todos.
- **Orden de despliegue**: la migración y el API pueden ir antes que el worker sin riesgo — un
  estado programado que nadie publica queda pendiente y lo recoge el barrido cuando el worker
  arranque, si aún está dentro de la ventana de gracia. Al revés también vale: el worker sin las
  tablas es un cron que falla al consultar, ruidoso pero inofensivo. No hay ventana peligrosa.
- **Rollback**: quitar el cron del worker deja de publicar y no rompe nada más; las tablas se quedan
  con sus filas y la pantalla sigue leyéndolas.

## Preguntas abiertas (no bloqueantes)

- **¿30 minutos de gracia es lo correcto?** Es una conjetura de partida, como los cinco minutos de
  barrido de las alertas. Con un registro de `skipped_late` a la vista, el número se corrige con
  datos en vez de con opinión.
- **¿90 días?** Igual. Es el orden de magnitud correcto; el valor exacto sale de mirar la
  distribución real de `max(sent_at)` de un tenant con volumen.
- **¿Publicación manual "ahora"?** Fuera de v1 a propósito, para que el cron sea el único camino que
  hay que probar. Cabe después como una franja de `on_date` = hoy con el minuto actual, sin tocar
  nada del modelo — que es la señal de que el modelo está bien.
- **¿Reintento de una publicación `failed`?** Hoy no: la emisión está reclamada, así que no se
  reintenta sola. Reintentar exige decidir si se libera la clave, y liberar una clave de unicidad es
  la clase de cosa que merece su propio change y sus propias pruebas.
- **¿Estadísticas?** La tabla de publicaciones ya deja el rastro para responder "cuántos estados
  saqué este mes y a cuánta gente". Interesante y prescindible.
