> Lee `design.md` antes de empezar. El change son **dos defensas y un motor tonto**: sin la
> coincidencia por palabra completa (grupo 1) y sin los dos gates (grupo 4) esto es un keyword-bot de
> 2010, y el módulo ya rechazó por escrito construir eso. El resto es fontanería alrededor.
>
> Orden recomendado: 1 → 2 → 3 → 4 → 5 (backend completo y probado) → 6 → 7. El grupo 8 se puede
> hacer en cualquier momento.

## 1. Backend — el matching, como funciones puras

> Viven en `messaging/domain/faq.py`, sin base, sin red y sin reloj: quien llama trae los valores.
> Mismo criterio que `templates.py`. Se prueban en `tests/modules/messaging/test_faq_matching.py`
> **sin levantar la app**, y esa suite es la que sostiene el change entero.

- [x] 1.1 `normalize(text)`: minúsculas, tildes fuera, signos a espacio, espacios colapsados. Los dos
      lados reciben el MISMO tratamiento (que `mañana` → `manana` da igual; lo que importa es que
      coincida consigo mismo)
- [x] 1.2 `matches(trigger, message)`: palabra o frase completa, por acolchado con espacios y
      contención — nunca substring, nunca regex. Insensible a singular/plural probando el trigger con
      y sin `s`/`es`. **Sin *stemming***: si `pago` llega a encontrar `pagué`, el change ha fallado
- [x] 1.3 `first_match(faqs, message)`: primera FAQ **encendida** cuyo algún trigger coincida; el
      orden de la lista es la prioridad
- [x] 1.4 Pruebas de la tabla de falsos positivos del diseño, una por fila, con el nombre del caso
      real: `"ya pagué y no me llegó"` no dispara `pago`, `"¿ya me lo enviaron?"` no dispara
      `envian`, `"¿hacen domicilios?"` sí dispara `domicilio`
- [x] 1.5 Prueba de que dos FAQs que coinciden dan UNA respuesta, la primera de la lista

## 2. Backend — `{hours_line}` y los marcadores de las FAQs

- [x] 2.1 `hours_line(windows, weekday, minute)` como función PURA en `business/domain/hours.py`:
      abierto → hasta qué hora cierra hoy; cerrado → que está cerrado y la próxima apertura; sin
      ventanas → `None`
- [x] 2.2 Registrar `hours_line` en `PLACEHOLDERS` y crear `FAQ_PLACEHOLDERS`
      (= identidad + `menu_link` + `next_opening` + `hours_line`). **No** los marcadores de pedido
- [x] 2.3 Resolverlo al enviar con la hora LOCAL de la sede (`business/application/clock.py`), nunca
      UTC — es la piedra que ya tropezó el saludo
- [x] 2.4 Un marcador sin dato se deja a la vista (regla de la casa), **salvo éste**: sin horarios
      cargados se omite la frase. Aquí el hueco lo lee un cliente, no el dueño en la pantalla —
      misma excepción que `{order_items}`

## 3. Backend — almacenamiento y validación

- [x] 3.1 Columna `faqs` JSON **nullable** en `whatsapp_autoreply_settings`. `null` = nunca las tocó;
      `[]` = decidió que ninguna. La distinción es el change, no un detalle: sin ella la FAQ borrada
      resucita
- [x] 3.2 Entidad/DTO `FaqEntry` con `id`, `name`, `enabled`, `triggers`, `text`. El `id` lo acuña el
      front; el backend valida unicidad y que no venga vacío
- [x] 3.3 Las cuatro sugeridas del diseño (§9) como constante del backend, **`enabled: false`**, y
      expuestas en la respuesta del API igual que `default_status_mapping`
- [x] 3.4 Validación al guardar, en `save_settings` y con el estilo del 422 que ya existe (nombrar al
      culpable): marcadores desconocidos contra `FAQ_PLACEHOLDERS`, FAQ sin nombre / sin trigger / sin
      texto, ids duplicados
- [x] 3.5 Rechazo de triggers reservados **por contención**, no por igualdad, con un error que enseñe
      (`"«cancelaciones» contiene «cancela», y esos mensajes los atiende una persona"`). Prueba
      explícita del caso `cancelaciones`: es el callejón sin salida que esto existe para evitar
- [x] 3.6 Migración **0031_whatsapp_faqs** (up/down/up en Postgres, sin deriva): columna `faqs`
      nullable. Los tenants existentes quedan en `null`.
      **Corrección sobre el diseño**: no hace falta columna para el id de FAQ — la unicidad de las
      emisiones vive en una sola columna de texto (`dedupe_key`), así que `faq:<conv>:<id>` entra
      sin tocar el esquema (`emission_key` gana un `detail`)

## 4. Backend — los gates y el engarce

- [x] 4.1 Subir `OPT_IN_WORDS`, `HANDOFF_WORDS` y `REFUND_WORDS` a `shared/customer_channel/`, junto
      a `CUSTOMER_STATES`; `assistant` pasa a leerlas de ahí. **Sin cambio de comportamiento**: las
      pruebas del asistente tienen que seguir pasando sin tocarlas
- [x] 4.2 Puerto + consulta "¿tiene este contacto un pedido vivo?": por `orders.whatsapp_contact_id`,
      no entregado/cancelado/cerrado, dentro de `idle_hours`. Comprobar que la columna está indexada y
      añadir el índice si no
- [x] 4.3 Gate de persona/cancelar/devolver **antes** de mirar triggers
- [x] 4.4 Gate de pedido vivo, con **fallo → silencio** (asimetría deliberada con el aviso de
      cerrado: aquí el silencio es el statu quo). Traza en el log diciendo QUÉ gate calló — es lo
      único que va a explicar un "no contesta" en soporte
- [x] 4.5 Reclamo de emisión `faq:<conversación>:<id>` con `try_claim_emission`, antes de enviar
- [x] 4.6 Engarce en `MessagingService.handle_inbound`: aprovechar el `bool` que `_assist` ya devuelve
      y hoy descarta → `if not handled: await self._faq(...)`. Nunca puede hacer fallar la recepción
      del mensaje (mismo trato que `_greet` y `_assist`)
- [x] 4.7 Sólo `greeted`. Prueba de que el PRIMER mensaje que coincide con un trigger recibe **sólo
      el saludo** (sale gratis porque el estado se lee antes de saludar, pero hay que fijarlo: es lo
      que se rompe al refactorizar)
- [x] 4.8 Prueba de que una conversación en `human` y otra en `bot` no reciben FAQ
- [x] 4.9 Prueba de que **cerrado sí contesta**, y de que no se añade ni una palabra al texto del
      tenant

## 5. Backend — pruebas de extremo a extremo

- [x] 5.1 Webhook entrante sobre conversación `greeted` con trigger → un mensaje saliente, persistido
      en el hilo como `system`, y la conversación **sigue en `greeted`** y sigue en la bandeja
- [x] 5.2 Dos entrantes con la misma pregunta → un solo saliente (el reclamo manda)
- [x] 5.3 Contacto con pedido vivo → cero salientes aunque el trigger coincida
- [x] 5.4 Tenant en `null` → las sugeridas llegan apagadas y **no** sale ninguna FAQ hasta encender
      una. Es la prueba de que instalar el change no cambia el comportamiento de nadie
- [x] 5.5 `ruff`, `mypy` y la suite completa en verde

## 6. Frontend — `FaqSection.vue`

> Patrón visual de `StatusMappingSection.vue`. Nada de librerías nuevas. Mono para etiquetas, el
> color reservado para calor y estado.

- [x] 6.1 Tipos `FaqEntry` / `FaqSettings` en `services/messaging.api.ts` y `faqs` + `default_faqs`
      en el contrato de la respuesta
- [x] 6.2 Espejo del matching en `lib/whatsappAutoreply.ts` (normalizar + palabra completa) para la
      vista previa, con el comentario de rigor: la verdad es el 422
- [x] 6.3 `materializeFaqs(saved, defaults)` respetando `null` ≠ `[]` — no copiar la fusión por clave
      de `status_mapping`, que aquí resucita lo borrado
- [x] 6.4 Tarjeta colapsable: header con **puesto en cifra mono** + nombre + toggle; el nombre se
      **edita dentro** de la tarjeta expandida, no en el header (no cabe en móvil con las flechas)
- [x] 6.5 Chips de triggers: añadir con Enter, quitar con "×", normalización visible (lo que se
      guarda es lo que se compara)
- [x] 6.6 Textarea del texto con los chips de marcadores y el aviso de marcador inexistente, como en
      `GreetingSection`
- [x] 6.7 Flechas ↑↓: deshabilitadas en los extremos, con `aria-label` que nombre la FAQ, y
      **reenfocar el control tras mover** (si no, el foco se va al `body` al llegar al extremo)
- [x] 6.8 "+ Agregar FAQ" (nace expandida y vacía) y borrar con confirmación
- [x] 6.9 "Restaurar sugeridas" con confirmación: reemplaza la lista
- [x] 6.10 Texto de ayuda con las condiciones de silencio **y** con "las FAQs sí contestan fuera de
      horario". Es entregable, no decoración: sin esto el dueño prueba con un pedido abierto y
      concluye que está roto
- [x] 6.11 `placeholderErrors` extendida para incluir los textos de las FAQs encendidas (las apagadas
      no bloquean el guardado, igual que los avisos apagados)

## 7. Frontend — integración y pruebas

- [x] 7.1 Cuarta sección en `WhatsAppAutoreplyView.vue`, dentro del `dirty` y del guardado
- [x] 7.2 Mostrar el 422 del backend tal cual en la barra de guardado (ya lo hace `saveError`)
- [x] 7.3 Pruebas de `FaqSection`: mover cambia el orden emitido, borrar todo deja `[]`, trigger
      reservado enseña el mensaje del servidor, marcador inexistente apaga el guardado
- [x] 7.4 Pruebas del espejo en `lib/__tests__/whatsappAutoreply.spec.ts`: la misma tabla de falsos
      positivos que el backend, para que las dos implementaciones no deriven
- [x] 7.5 `pnpm type-check`, `pnpm lint`, `pnpm test:unit` en verde

## 8. Documentación

- [x] 8.1 `docs/messaging/ROADMAP.md`: añadir las FAQs por palabra clave a la tabla de motores a 0
      tokens — es la pieza que faltaba en la tesis "lo gratis primero"
- [x] 8.2 Nota en `messaging/application/use_cases/autoreply.py` explicando por qué el matching por
      palabras clave existe aquí **sin** contradecir la regla #1 del módulo: el saludo sigue sin leer
      el texto, y lo que lee texto vive detrás de dos gates
- [x] 8.3 `docs/messaging/` — documentar `{hours_line}` y la lista de triggers sugeridos
