> Lee `design.md` antes de empezar. Este change es **un cron tonto rodeado de cuatro defensas**. El
> cron es media tarde; las defensas son el change. Sin el tope, la ventana de 90 días, el opt-out y la
> exclusión de `@lid` (grupos 3 y 4), esto es una máquina de quemar el número de WhatsApp del negocio
> — y si el número cae, cae el canal entero, no sólo esta feature.
>
> Dos decisiones son contraintuitivas y están en el diseño con su porqué. Si te parece que están mal,
> lee la decisión antes de "arreglarlas":
>
> - **La clave de emisión NO lleva el id de la franja** (decisión 6). Ponerlo republica todo con
>   cualquier guardado.
> - **No hay campo `kind` ni bandera `only_when_open`** (decisiones 5 y 7). Las franjas son el
>   horario; el selector de días es la respuesta.
>
> Orden: 0 → 1 → 2 → 3 → 4 → 5 → 6 (backend completo y probado) → 7 → 8 → 9. El grupo 10 va al final
> y **no es opcional**: es lo único que comprueba que esto funciona de verdad.

## 0. Spike: ¿acepta `statusJidList` un `@lid`?

> Veinte minutos contra la instancia real, **antes** de escribir código. Todo el grupo 4 depende de
> la respuesta, y es más barato saberlo ahora que rehacerlo después. Si la respuesta es sí, el filtro
> de `@lid` se cae y su contador queda en cero; el resto del change no cambia.

- [x] 0.1 Publicar un estado de prueba a un `statusJidList` con un solo `@lid`, contra la instancia
      real, y mirar el resultado **en un teléfono** — no en el 201 de la respuesta, que miente por
      diseño (`Promise.allSettled`)
      → **2026-08-09: NO lo recibe.** La hipótesis del diseño era la correcta; el filtro se queda
- [x] 0.2 Apuntar el resultado en `design.md`, decisión 2, con fecha. Si funciona, dejar escrito que
      el filtro se puede quitar y por qué se diseñó con él
      → anotado en `design.md`, decisión 2, con la fecha y con qué habría que tocar si algún día
      cambiara (un `continue` en `resolve_audience`)

## 1. Backend — el horario, como funciones puras

> Viven en `messaging/domain/status_schedule.py`, sin base, sin red y sin reloj: quien llama trae la
> hora local. Mismo criterio que `templates.py` y que `business/domain/hours.py`. Se prueban en
> `tests/modules/messaging/test_status_schedule.py` **sin levantar la app**.

- [x] 1.1 `StatusSlot`: `minute` (desde medianoche, local) + **exactamente uno** de `weekday` (0=lunes)
      o `on_date`. Los dos o ninguno es un error de validación
- [x] 1.2 `due_slots(slots, local_now, grace_minutes)`: las franjas vencidas **hoy** en local, cada una
      con si está dentro de la gracia o fuera. Una sola función devuelve las dos clases; separarlas
      invita a que una de las dos se olvide de la gracia
      → firma final `due_slots(slots, local_date, now_minute, grace_minutes)`: recibe la FECHA y
      deriva de ella el día de la semana, así los dos no pueden discrepar y no se puede colar un
      instante UTC "que parece funcionar". Colapsa por minuto (ver docstring)
- [x] 1.3 `emission_key(status_id, local_date, minute)` → `status:<id>:<YYYY-MM-DD>:<minuto>`. Función
      pura y **el único sitio** donde se construye la clave. Sin `slot_id`, ver decisión 6
- [x] 1.4 Pruebas del cruce de medianoche: una franja del lunes a las 20:00 en UTC-5 vence el **lunes**
      local. Si esta prueba pasa contra `datetime.now(UTC)`, la prueba está mal escrita
- [x] 1.5 Prueba de que siete franjas de `weekday` cubren "todos los días" y que una `on_date` pasada
      no vence nunca

## 2. Backend — modelo y migración

- [x] 2.1 `WhatsAppStatusModel` (BranchScoped): `type`, `content`, `bg_color`, `font`, `caption`,
      `media_url`, `active`, `created_by`
- [x] 2.2 `WhatsAppStatusSlotModel`: `status_id`, `weekday` nullable, `on_date` nullable, `minute`, con
      **CHECK de exclusión mutua en la base**. Que la invariante viva en el esquema y no sólo en el
      dominio es lo que impide que una inserción de un script la rompa
      → verificado contra Postgres: un INSERT con día Y fecha da
      `violates check constraint "ck_whatsapp_status_slots_weekday_xor_date"`.
      Lleva `BranchScopedMixin` (no `Base` pelado): mismo trato que `whatsapp_messages`, que
      también repite tenant/sede sobre un padre que ya los tiene, porque el filtro automático de
      tenancy sólo protege lo que hereda el mixin
- [x] 2.3 `WhatsAppStatusPublicationModel`: `status_id`, `fired_for_date`, `minute`, `state`
      (`published` | `failed` | `skipped_late`), `recipient_count`, `excluded_no_number`,
      `excluded_opted_out`, `excluded_inactive`, `excluded_by_cap`, `provider_message_id`,
      `created_at`. Cuatro columnas de exclusión y no una suma: el spec exige itemizarlas
      → nombre final `addressed_count` (no `recipient_count`), + `late_by_minutes` para que un
      `skipped_late` pueda decir cuánto tarde llegó en vez de ser un silencio con fila
- [x] 2.4 Nombrar `recipient_count` de forma que **no se pueda leer como "llegó a"**. Es "a cuántos se
      dirigió". Comentario en el modelo diciéndolo, porque es lo que evita que la UI de mañana escriba
      "visto por"
- [x] 2.5 `whatsapp_contacts.status_opt_out: bool`, default `false`, `NOT NULL`
- [x] 2.6 Migración `0047` (o el siguiente libre) con las tres tablas, la columna y el CHECK. Verificar
      que ningún change activo haya tomado el número
      → `0047_whatsapp_scheduled_statuses`, aplicada y revertida contra Postgres local. `branch_id`
      va con **RESTRICT**, que es lo que declara el mixin: 0046 escribió CASCADE y por eso
      `alembic check` ya venía marcando desfase en `table_bills`. Mis tres tablas salen limpias
      (`alembic check` ya fallaba antes de este change, por otras siete tablas ajenas)
- [x] 2.7 Registrar los modelos en `shared/models_registry.py` — sin eso el worker revienta al arrancar
      por las FK entre módulos
      → ya estaba: el registro importa el MÓDULO `messaging.infrastructure.models`, así que las
      clases nuevas entran solas. Confirmado porque `alembic check` ve las tres tablas

## 3. Backend — la audiencia y sus cuatro reducciones

> Aquí está el riesgo del change. Se prueba con datos, no a ojo:
> `tests/modules/messaging/test_status_audience.py`.

- [x] 3.1 `status_audience(tenant, branch, window_days)` en el repositorio, sobre la forma de
      `list_contactable`: contactos con entrante en **esa sede**, sin opt-out, con
      `max(sent_at) >= hoy − window_days`, **ordenados por `max(sent_at) desc`**
      → partido en dos: `list_status_candidates` (SQL: join + group_by + orden, y TRAE el opt-out y
      la recencia como hechos) y `resolve_audience` (puro: las cuatro reducciones y sus cuentas).
      La consulta NO filtra opt-out ni inactividad porque filtrar ahí hace imposible CONTARLOS, y
      las cuentas por separado son requisito. El spec delta de `whatsapp-messaging` se corrigió: se
      contradecía consigo mismo en este punto
- [x] 3.2 El orden es requisito, no comodidad: es lo que hace que el tope conserve a los más recientes.
      Prueba explícita de ello
- [x] 3.3 Prueba de que un contacto que escribió **sólo a otra sede** NO entra. Es la asimetría con
      `is_reachable`, que es deliberadamente por negocio y **se queda como está**
- [x] 3.4 Separar los `@lid`: no se descartan callados, se devuelven contados aparte. Un contacto cuyo
      `phone` contiene `@` es un `@lid` (`shared/domain/phones.py:40`)
- [x] 3.5 Construir el JID de los buenos: dígitos + `@s.whatsapp.net`. Dejar en el docstring que
      reconstruir un JID fue una trampa conocida del canal y por qué aquí no hay alternativa —
      `provider_remote_jid` es por mensaje, no por contacto
- [x] 3.6 Aplicar el tope **al final**, después de todo lo demás, devolviendo cuántos se omitieron
- [x] 3.7 `WHATSAPP_STATUS_RECIPIENT_CAP` y `WHATSAPP_STATUS_INACTIVITY_DAYS` (default 90) en settings,
      con **techo absoluto** que la configuración no puede superar. Prueba de que el techo gana
      → `whatsapp_status_recipient_cap` (200), `whatsapp_status_inactivity_days` (90) y
      `whatsapp_status_grace_minutes` (30). El techo es `ABSOLUTE_RECIPIENT_CEILING = 500`,
      constante del DOMINIO y no ajuste: un techo configurable no es un techo
- [x] 3.8 Prueba de la tabla completa del diseño: 340 → 12 `@lid` → 4 opt-out → 118 inactivos → tope
      200 → 6 omitidos. Los cinco números salen por separado
      → `test_the_full_reduction_table_from_the_design`, y además comprueba que los cinco SUMAN con
      el total: cada contacto cae en exactamente un cubo, el primero que lo excluye

## 4. Backend — el opt-out

- [x] 4.1 Endpoint para marcar y desmarcar `status_opt_out` de un contacto, gateado con
      `messaging.attend` (no `manage`: lo usa quien atiende, ver decisión 4)
      → `PUT /messaging/conversations/{id}/status-opt-out`, se entra por la CONVERSACIÓN (la
      petición llega en el chat) y la marca es del CONTACTO (aplica a todas las sedes)
- [x] 4.2 Exponer `status_opt_out` en el contacto que ya lee la bandeja
- [x] 4.3 Prueba de que marcar no toca el estado de la conversación, no la saca de la bandeja y no
      impide responder
      → las 3 pruebas pasan. Trampa encontrada al escribirlas: los permisos efectivos se cachean
      con TTL (`RbacPermissionCache`), así que una petición autenticada ANTES de `grant_only` deja
      cacheados los del admin y el 403 nunca llega. Por eso la prueba de permisos lee el id de la
      conversación de la base, no del API
- [x] 4.4 Prueba de que el opt-out aplica a **todas** las sedes del negocio, aunque la audiencia sea
      por sede

## 5. Backend — `send_status` en el gateway

- [x] 5.1 Método `send_status(session, card, jids)` en el puerto del gateway, junto a `send_text` y
      `send_media`
- [x] 5.2 Implementación en `BridgeWhatsAppGateway`: `POST /message/sendStatus/{instance}`, cabecera
      `apikey`, payload `{type, content, statusJidList, backgroundColor?, font?, caption?}`. Todo lo
      específico del puente se queda en ese fichero, como el resto
- [x] 5.3 Pasarlo por `GuardedWhatsAppGateway`: puente inalcanzable y puente **sin configurar** son dos
      errores distintos, como ya lo son para `send_text`
      → el guard es passthrough, con el porqué escrito: un estado no le escribe a NADIE, así que no
      hay a quién preguntarle `is_reachable`. La invariante se conserva aguas arriba, por
      construcción de la audiencia. Pasa por el guard igual para que la comprobación del PUENTE sea
      la misma en los tres verbos
- [x] 5.4 Dejar escrito en el docstring que el puente parte en lotes de 10 y se come los fallos de los
      lotes en un `Promise.allSettled`, así que **un 201 no significa que llegó a todos**. Es la razón
      del vocabulario del grupo 8
- [x] 5.5 Prueba con cliente httpx falso: payload correcto, y `MessageDeliveryError` en 4xx/5xx
      → 9 pruebas en `test_bridge_status.py`, incluida
      `test_a_partial_batch_failure_still_looks_like_success`, que deja constancia de la limitación
      que fija el vocabulario de toda la UI. `publish_status` devuelve `str | None`: "no sabemos el
      id" y "es la cadena vacía" son distintos

## 6. Backend — casos de uso, cron y API

- [x] 6.1 Validación al guardar: un estado de texto sin `bg_color` o sin `font` es un 422 que nombra lo
      que falta. **Al guardar, no al publicar** — a las once, en el worker, no hay nadie mirando
- [x] 6.2 Guardar las franjas **borrando e reinsertando**, como `operating_hours`. Es lo correcto para
      un conjunto que se edita entero, y es exactamente lo que obliga a la clave de la tarea 1.3
- [x] 6.3 `publish_status(status_id, local_date, minute)`: reclama la emisión → resuelve audiencia →
      lotes de 10 con jitter → escribe la fila de publicación con los cinco números
      → **CORREGIDO respecto al diseño: NO se trocea la audiencia.** Evolution reenvía sus tandas
      internas con el MISMO `messageId` (`service.ts:2271`), que es lo que hace que el espectador vea
      UNA historia. Trocear por nuestra cuenta habría convertido 200 destinatarios en 20 historias
      idénticas. Se manda una sola llamada con la lista entera, y el jitter va **entre estados
      distintos** del mismo barrido. `batched()` se cayó; queda `publication_calls()`, que cuenta el
      coste sin partir nada
- [x] 6.4 La franja fuera de gracia: `skipped_late` **y reclamar la emisión igual**, para que el barrido
      del minuto siguiente no la reconsidere para siempre
      → apareció un CUARTO estado que el spec no tenía: `skipped_empty`, cuando no queda nadie tras
      las cuatro reducciones. No es `failed` (nada se rompió y culpar al puente manda a mirar donde
      no está el problema) ni `published` (no salió). Misma razón que `skipped_late`: no publicar
      tiene que dejar fila
- [x] 6.5 `WHATSAPP_STATUS_GRACE_MINUTES` (default 30) en settings — hecho ya en el grupo 3
- [x] 6.6 Cron `sweep_due_statuses` en el worker de **alertas**, cada minuto, `unique=True`, en
      `ALERTS_QUEUE`. Nada de worker nuevo (decisión 8)
- [x] 6.7 **Reescribir el docstring del worker de alertas**, no pegarle un párrafo: pasa a tener dos
      responsabilidades, y la razón del "EJECUTA EXACTAMENTE UNO" pasa a ser doble — trabajo duplicado
      en alertas, y **publicaciones duplicadas** en estados. La segunda es más grave, y hay que
      encontrarla ahí antes de escalar el Deployment a dos réplicas
      → reescrito entero: el "EJECUTA EXACTAMENTE UNO" pasa a tener DOS motivos numerados, con el de
      estados marcado como el grave, y el docstring explica por qué el cron vive aquí y no en un
      worker propio
- [x] 6.8 Todo el barrido en hora local vía `business/application/clock.py`. Cero `datetime.now(UTC)`
      en el camino de decisión
- [x] 6.9 Router: CRUD de estados + franjas, previsualización de la audiencia (los cinco números),
      historial de publicaciones. Todo con `messaging.manage`
- [x] 6.10 Subida de la imagen a R2 por `presign_put`, como `media_store.py`. A Evolution le va una
      **URL**, nunca base64
      → `store_status_media` con prefijo propio `whatsapp-status/` (una imagen de estado no pertenece
      a ninguna conversación) y sin id del estado en la clave: se sube ANTES de que el estado exista.
      El PUT firmado se extrajo a `_upload`, compartido con el multimedia de conversación
- [x] 6.11 Pruebas de integración: dos barridos en el mismo minuto publican una vez; guardar el estado
      a las 11:05 no republica el de las 11:00; dos franjas el mismo día publican dos veces; la misma
      franja publica otra vez al día siguiente
      → 12 en `test_status_publishing.py` (las cuatro + gracia + los cuatro finales + el cruce de
      medianoche con el reloj sustituido) y 17 en `test_statuses_api.py`. 520 pasan entre
      `messaging` y `alerts`

## 7. Frontend — el compositor

- [x] 7.1 Vista `WhatsAppStatusesView.vue` + ruta + entrada de navegación, gateada con
      `messaging.manage`
- [x] 7.2 La vista previa **es** la tarjeta: color de fondo y fuente reales, proporción de móvil. No es
      una aproximación — son los dos únicos parámetros que el proveedor exige, así que una previa que
      los pinte distinto miente sobre lo único que podría equivocar
      → el fondo va por `style` y no por clase: una clase tendría que existir para cada color, y en
      el momento en que un color no tuviera clase la tarjeta se pintaría de otro SIN fallar. El pie
      enseña `#color · Fuente` en mono para que el dueño pueda relacionar previa y envío.
      Honestidad de la previa: promete la FORMA de la fuente (serif/estrecha/manuscrita), no el tipo
      exacto — no tenemos las fuentes de WhatsApp, y prometerlas se notaría en el teléfono
- [x] 7.3 Selector de color y de fuente, con guardado bloqueado si falta cualquiera de los dos
- [x] 7.4 Modo imagen: subida, previa con el pie
- [x] 7.5 Semana a mano, siete días + horas, en la línea del riel de servicio de `/staff`. Sin
      librerías nuevas
- [x] 7.6 Franja de fecha concreta, visualmente distinta de las semanales
- [x] 7.7 **Sin selector de "una vez / recurrente"**. Marcar los siete días *es* "todos los días"
      → hay un botón "Todos" que marca los siete de golpe: es el atajo del caso más común, no un
      modo. La prueba lo verifica sobre los CONTROLES (cero `<select>`, cero radios), no sobre la
      prosa — mi primera versión falló porque "ninguna vez" del historial contenía "una vez"

## 8. Frontend — audiencia y registro, con el vocabulario correcto

- [x] 8.1 Antes de publicar: los cinco números **itemizados**, nunca sólo el final. "200 de 206 · 12 sin
      número visible · 4 no quieren · 118 inactivos · 6 omitidos por el tope"
- [x] 8.2 Audiencia vacía: decir **por qué**, no un cero pelado
- [x] 8.3 Historial por estado: publicado / falló / omitido, con la hora y el motivo del omitido
- [x] 8.4 **Prohibido** "visto por" y "entregado a". Sólo "enviado a N". Que quede en un comentario del
      componente, porque es la clase de texto que alguien "mejora" en seis meses
      → `addressedLabel()` es el único sitio que lo redacta, con el porqué en su docstring, y dos
      pruebas lo vigilan: una sobre la función y otra sobre el historial renderizado
- [x] 8.5 Los tres resultados legibles sin color (texto o forma, no sólo tono)
      → CUATRO, no tres (apareció `skipped_empty`), y cada uno con glifo propio vía
      `publicationGlyph()`: ✓ ✕ ◷ ○. "Se pasó la hora" y "sin audiencia" se cuentan distinto porque
      se arreglan de formas opuestas
- [x] 8.6 Tags de audiencia en mono; el color reservado al resultado

## 9. Frontend — el opt-out en la bandeja

- [x] 9.1 Interruptor en la ficha del contacto del hilo, gateado con `messaging.attend`
- [x] 9.2 Mostrar el estado actual en el hilo
- [x] 9.3 Prueba de que marcar no altera el hilo ni el compositor

## 10. Cierre — y la prueba que ninguna suite puede dar

- [x] 10.1 `make test` backend y frontend, type-check y lint
      → acotado a los módulos tocados (la suite completa tarda demasiado): backend
      `tests/modules/messaging/ tests/modules/alerts/` = **520 pasan**; frontend los 10 ficheros de
      messaging = **149 pasan**. `ruff`, `eslint`, `oxlint` y `vue-tsc` limpios. `mypy` sólo con los
      2 errores preexistentes de `media_store.py` (mismo código, movido por el refactor de `_upload`)
- [x] 10.2 **Publicar un estado real y mirarlo en un teléfono que tenga el número guardado.** No hay
      forma automatizada de comprobar esto: Evolution no devuelve vistas, y devuelve 201 aunque la
      mitad de los lotes se hayan caído. Esta casilla es la única evidencia de que el change funciona
      → **verificado en teléfono el 2026-08-09**
- [x] 10.3 Mirar el mismo estado en un teléfono que **no** tenga el número guardado, para confirmar en
      la práctica lo que el diseño afirma: no lo ve. Es lo que justifica las cuatro defensas
      → **verificado el 2026-08-09**: sin el número guardado no aparece el estado
- [x] 10.4 Arrancar con el tope **bajo** y subirlo mirando el número, no al contrario
      → `whatsapp_status_recipient_cap = 200` por defecto, con `ABSOLUTE_RECIPIENT_CEILING = 500` de
      techo en el dominio que ningún ajuste puede superar. Ventana de inactividad 90 días
- [x] 10.5 Comprobar en k8s que el worker de alertas sigue con **una** réplica. Dos publican dos veces,
      y la tarea 6.7 existe para que quien escale lo lea antes
      → `k8s/workers.yaml`: `replicas: 1` + `strategy: Recreate` (lo segundo es la mitad que se
      olvida: RollingUpdate levanta el pod nuevo antes de tumbar el viejo). Añadida al aviso de
      cabecera la SEGUNDA razón, marcada como la grave: ese proceso publica los estados, y dos
      réplicas sacarían el mismo estado dos veces al teléfono de cada contacto
