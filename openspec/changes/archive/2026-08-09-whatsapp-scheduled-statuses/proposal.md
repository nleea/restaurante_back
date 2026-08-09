## Why

El canal sólo sabe **reaccionar**. Las cuatro respuestas que existen —saludo, avisos de estado,
FAQs, asistente— salen todas porque alguien escribió primero o porque un pedido se movió. Y eso no
es una carencia: es la invariante del módulo, escrita y defendida en cada change anterior —
**nunca iniciar una conversación**.

Un restaurante, en cambio, tiene una cosa que decir todos los días a las once y hoy no tiene por
dónde decirla: el menú del día. La única salida que existe es que una persona lo pegue a mano en la
app de WhatsApp del teléfono del negocio, y por eso en la práctica no se hace, o se hace tarde.

Los estados son la respuesta, y lo interesante es **por qué no rompen la invariante**:

```
mensaje directo   →  aparece en el chat de alguien       →  inicia conversación   ❌
estado            →  aparece en la pestaña "Novedades"   →  el contacto lo abre
                                                              si quiere           ✅
```

Un estado no aterriza en ninguna conversación, no espera respuesta, no saca ningún hilo de la
bandeja y caduca solo a las 24 horas. Es lo primero que este módulo puede emitir sin que nadie
pregunte, sin contradecir la regla que lo sostiene.

**El contrapeso, y hay que decirlo antes que nada:** la invariante sobrevive *en la letra*, el
riesgo sobrevive *en los hechos*. `autoreply.py:174` ya lo tiene escrito — *"el volumen de salida es
lo que hace que WhatsApp mire un número"* — y esto es volumen de salida no solicitado sobre un
puente no oficial. Evolution parte la lista de destinatarios en **lotes de diez** y hace un
`sendMessage` por lote (`whatsapp.baileys.service.ts:2224`): 400 contactos son 40 envíos a
`status@broadcast`. Ese número es el que puede costar la cuenta del negocio, y es la razón de que
este change traiga tope, ventana de inactividad y opt-out **desde el primer día** en vez de
dejarlos para después. Sin las tres, no vale la pena hacerlo.

Y el aviso de arriba del todo: el router de Evolution lleva un `// TODO: Revisar funcionamento do
envio de Status` encima del endpoint (`sendMessage.router.ts:100`). Upstream no lo garantiza.
Nosotros tampoco vamos a poder garantizarlo (ver `design.md`, decisión 10).

## What Changes

- **Un estado se compone, no se "escribe".** Evolution exige, para `type: 'text'`,
  `backgroundColor` **y** `font` (`whatsapp.baileys.service.ts:2690`): sin ellos es un 400. Así que
  el objeto de dominio es una tarjeta —texto + color + fuente— o una imagen con pie, no una cadena.
- **La audiencia son los contactos que escribieron a ESE número**, no al negocio. La sesión de
  WhatsApp es por sede (`WhatsAppSessionModel(BranchScopedMixin)`) y quien escribió a la sede A no
  tiene guardado el número de la sede B, así que jamás verá su historia. Se reusa la forma de
  `list_contactable(tenant, branch)`, que ya exige "escribieron ellos primero" y ya ordena por
  actividad reciente.
- **Los contactos con JID de privacidad (`@lid`) quedan FUERA de la audiencia, y se cuentan.**
  `phone` no siempre es un teléfono: `shared/domain/phones.py:35` devuelve `123456@lid` intacto a
  propósito, porque es lo único con lo que se le puede escribir a ese contacto. Si eso vale en
  `statusJidList` es un **desconocido**, y el modo de fallo es silencioso. Excluir visiblemente
  gana a incluir y fallar callado.
- **Tope de destinatarios y ventana de inactividad de 90 días.** El tope es la red de seguridad
  (configurable, con techo absoluto); la ventana es el criterio: quien escribió una vez hace ocho
  meses probablemente ya no te tiene guardado, así que es volumen sin audiencia.
- **La truncación es ruidosa, nunca silenciosa.** Antes de publicar, la pantalla dice "200 de 206";
  después, la fila de publicación guarda `recipient_count` y `skipped_count`. Un "publicado ✓" sobre
  200 de 340 se lee como cobertura total, y no lo es.
- **Opt-out por contacto**, columna nueva en `whatsapp_contacts` y interruptor en la bandeja. Quien
  escribió para pedir un almuerzo no pidió recibir el menú de mañana, y hoy la única forma de
  sacarlo de la lista sería borrar el contacto, que se lleva su historial por delante.
- **El horario son filas, no una cadena de cron.** Se copia `operating_hours` tal cual: una fila por
  franja, `weekday` 0=lunes…6=domingo, minutos desde medianoche, **hora local naive**, y los
  cálculos como funciones puras del dominio. "Todos los días a las 11:00" son siete filas.
- **Una franja es un día de la semana O una fecha concreta, nunca las dos.** Con eso "el 15 a las
  18:00" y "todos los viernes a las 18:00" son la misma tabla, la misma consulta y la misma clave de
  emisión — y **no hace falta un campo `kind`**. Un `kind` sería un segundo sitio donde se decide el
  mismo hecho, y cuando dos sitios deciden lo mismo el de abajo gana en silencio.
- **La clave de emisión va sobre el reloj de pared, no sobre el id de la franja:**
  `status:<status_id>:<fecha_local>:<minuto>`. Es la decisión menos obvia del change y la que evita
  un reenvío masivo (ver `design.md`, decisión 6).
- **Lo publica el worker de alertas**, con un cron por minuto en su cola propia. Ni worker nuevo ni
  Deployment nuevo: ese proceso **ya habla WhatsApp**
  (`alerts/infrastructure/whatsapp_escalation.py:43` importa el bridge y el guard) y su invariante
  documentada —*"EJECUTA EXACTAMENTE UNO"*— es literalmente el requisito de un programador de tareas.
- **Publicar es un trabajo, no una petición.** Veinte lotes con jitter no caben en un request: el
  endpoint valida, resuelve la audiencia, la cuenta y encola.
- **El barrido es autoritativo, y esta vez es lo único que hay.** Las alertas necesitan las dos
  vías (job para la latencia, barrido para la garantía). Un horario es intrínsecamente temporal: no
  hay nada que anunciar, así que se cae la mitad complicada del patrón.
- **Sin bandera de "sólo si estamos abiertos".** El selector de días de la semana ya es la respuesta:
  el dueño desmarca el lunes. Es el mismo argumento que mata el campo `kind`.
- **Una franja que venció hace demasiado no se publica: se registra como `skipped_late`.** El estado
  caduca a las 24 horas; sacar el menú del día a las tres de la tarde porque el worker estuvo caído
  desde las once es peor que no sacarlo. Pero se ve, no se calla.
- **Pantalla nueva** `/whatsapp/statuses`, con la vista previa **como la tarjeta real** —color de
  fondo y fuente de verdad— y el calendario semanal debajo con las franjas ocupadas, en la línea del
  riel de servicio de `/staff`. Mono para los tags de audiencia; el color reservado para el estado
  (programado / publicado / falló / omitido).

## Capabilities

### Added Capabilities

- `whatsapp-statuses`: componer un estado, programarlo por franjas, resolver su audiencia con las
  tres defensas, publicarlo por lotes y dejar constancia de lo que pasó. Capability propia y no
  ampliación de `whatsapp-autoreply` porque no comparte nada con ella: no lee mensajes entrantes, no
  depende del estado de una conversación, no tiene marcadores y no es una **respuesta**. El único
  mecanismo que reusa es la emisión única, que ya vive en `whatsapp-messaging`.
- `frontend-whatsapp-statuses`: el compositor con vista previa fiel, el calendario semanal, la
  cuenta de audiencia antes de publicar y el registro de publicaciones.

### Modified Capabilities

- `whatsapp-messaging`: gana el tercer verbo del gateway (`send_status`, junto a `send_text` y
  `send_media`, pasando igual por `GuardedWhatsAppGateway`), la consulta de audiencia por sede con
  sus tres filtros, y el opt-out por contacto. La tercera clase de clave de emisión encaja en el
  patrón que el docstring del modelo ya documenta.
- `frontend-whatsapp-inbox`: gana el interruptor de opt-out en la ficha del contacto. Es el sitio
  natural: quien pide no recibir más lo pide **en el chat**, y el que lo lee es quien atiende.

## Impact

- **Backend `messaging`**: entidades y funciones puras del horario en el dominio (mismo criterio que
  `templates.py` y que `business/domain/hours.py`: sin base, sin red, sin reloj); tres tablas
  nuevas; una columna en `whatsapp_contacts`; `send_status` en el bridge y en el guard; la consulta
  de audiencia; el router con `messaging.manage`.
- **Backend `alerts`**: un cron nuevo en el worker, en la cola `arq:queue:alerts` que ya existe. El
  docstring del worker hay que ampliarlo: pasa a tener dos responsabilidades y la razón del
  "exactamente uno" cambia de matiz.
- **Migración 0047** (o el siguiente número libre): `whatsapp_statuses`,
  `whatsapp_status_slots`, `whatsapp_status_publications`, y `whatsapp_contacts.status_opt_out`
  con default `false`. **Nadie estrena comportamiento**: sin estados creados, el cron no encuentra
  nada y el sistema se comporta exactamente igual que hoy.
- **Sin permiso nuevo**: `messaging.manage` ya existe y ya gatea el editor de autorespuestas
  (`messaging/infrastructure/api/router.py:91`), así que no hay que volver a sembrar el catálogo —
  que es lo que hace que una pantalla nueva dé 403 para todos.
- **Frontend**: vista nueva, ruta, entrada de navegación, el tipo del contrato y el interruptor en la
  bandeja. Sin librerías nuevas: el calendario y las franjas se hacen a mano, como el mes de `/staff`.
- **Almacenamiento**: la imagen de un estado va a R2 por el mismo camino presignado que el
  comprobante y el multimedia entrante (`media_store.py`), y Evolution recibe una **URL**, no
  base64. La URL es pública y opaca, con el mismo trato que ya tienen las otras dos.
- **Riesgo operativo, y es el real**: la cuenta de WhatsApp del negocio. Tope, ventana de 90 días,
  opt-out y jitter lo acotan; no lo eliminan. Si el número se cae, se cae el canal entero —bandeja,
  avisos de pedido, asistente—, no sólo esta feature. Eso justifica arrancar con el tope bajo y
  subirlo mirando, no al contrario.
- **Lo que NO vamos a poder decir**: cuántas personas vieron el estado. Evolution no devuelve vistas
  y los lotes fallan en silencio dentro de un `Promise.allSettled`. La UI dice "publicado", nunca
  "visto por N", y el `design.md` deja escrito exactamente qué podemos afirmar.

## Notes

Deuda de spec que se ve al escribir esto y queda **fuera de alcance**: `whatsapp-messaging` describe
el gateway en términos de "enviar un mensaje a un contacto alcanzable", y un estado no tiene
destinatario único ni pasa por el criterio de alcanzabilidad de `is_reachable` — que es
deliberadamente **no** por sede, mientras que la audiencia de un estado tiene que serlo. Este change
añade el verbo sin reescribir esa formulación; ponerla al día merece un `sync` propio para no
atribuirle a los estados un cambio de modelo que no es suyo.

El spike que debería ir **antes** de escribir código, y son veinte minutos contra la instancia real:
¿acepta `statusJidList` un `@lid`? Si la respuesta fuese sí, el filtro de la decisión 2 pasa de
"excluir" a "incluir", y es más barato saberlo antes que después.
