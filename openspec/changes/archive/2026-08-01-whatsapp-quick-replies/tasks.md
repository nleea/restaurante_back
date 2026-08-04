> Lee `design.md` antes de empezar. El change es **un calco de las FAQs con casi todo quitado**:
> misma fila, mismo `null` ≠ `[]`, misma validación de marcadores. Lo que NO se copia son los gates,
> la emisión única y el vocabulario reservado — no defienden de nada cuando el mensaje lo manda una
> persona. Si al terminar hay algo en el pipeline de entrada que menciona `quick_replies`, el change
> ha fallado.
>
> Orden recomendado: 1 → 2 → 3 (backend completo y probado) → 4 → 5 → 6. El grupo 7 al final.

## 1. Backend — dominio y validación, como funciones puras

> Viven en `messaging/domain/quick_reply.py`, sin base, sin red y sin reloj. Mismo criterio que
> `templates.py` y `faq.py`. Se prueban en `tests/modules/messaging/test_quick_replies.py` **sin
> levantar la app**.

- [x] 1.1 Entidad `QuickReply` con `id`, `name`, `text` y nada más. Sin `enabled` y sin `triggers`:
      los dos sólo significan algo cuando algo dispara solo (design §3). El `id` lo acuña la
      pantalla; el backend sólo garantiza que no se repita
- [x] 1.2 Topes como constantes del dominio: `MAX_QUICK_REPLIES = 20`, `MAX_QUICK_REPLY_CHARS = 1000`,
      `MAX_QUICK_REPLY_NAME_CHARS = 40`
- [x] 1.3 `validate_quick_replies(entries)`: id vacío, id repetido, nombre vacío, texto vacío, nombre
      o texto pasados de largo, y más de `MAX_QUICK_REPLIES` entradas. Cada error **nombra a la
      culpable** (`Respuesta rápida "Datos de Nequi": …`), con el estilo del 422 que ya existe
- [x] 1.4 Rechazo de marcadores reutilizando `_reject_unknown(text, frozenset(), where)`: con el
      conjunto permitido **vacío**, cualquier `{loquesea}` es desconocido. El mensaje de error tiene
      que decir *por qué* (las respuestas rápidas no interpolan), no sólo que está mal
- [x] 1.5 Las sugeridas del diseño como constante `SUGGESTED_QUICK_REPLIES`, y una prueba de que
      **pasan su propia validación** — una sugerida inválida es un botón que rompe la pantalla
- [x] 1.6 Pruebas: lista vacía es válida, 21 entradas no, dos ids iguales no, `{link}` no, `{nombre}`
      tampoco (el rechazo no depende de que el marcador exista)

## 2. Backend — almacenamiento

- [x] 2.1 Migración `0034`: columna `quick_replies` JSON **nullable** en
      `whatsapp_autoreply_settings`. Sin backfill y sin `server_default`: los tenants existentes
      nacen en `null`, que es exactamente "nunca las configuré"
- [x] 2.2 Campo en `WhatsAppAutoreplySettingsModel` con docstring que diga con todas las letras que
      **esto no contesta solo** y por qué vive en una tabla que se llama `autoreply` (design §1).
      Es la mitigación del único riesgo de lectura del change, no un comentario decorativo
- [x] 2.3 Campo `quick_replies: list[QuickReply] | None` en la entidad `AutoreplySettings`, y
      round-trip en el repositorio: `None` se guarda y se lee como `None`, `[]` como `[]`
- [x] 2.4 Prueba de repositorio del `null` ≠ `[]`: guardar `[]`, releer, y comprobar que **no** sale
      `None` (y al revés). Es el bug que resucita plantillas borradas

## 3. Backend — API

- [x] 3.1 `QuickReplySchema` (`id`, `name`, `text`) y campo opcional `quick_replies` en
      `AutoreplySettingsSchema`, con el mismo trato de `None` que `faqs` en `from_settings` /
      `to_settings`
- [x] 3.2 Validar en el guardado de ajustes, junto a `_validate_faqs`. Un 422 deja la lista guardada
      **intacta**: prueba explícita de que un guardado inválido no borra lo anterior
- [x] 3.3 `suggested_quick_replies` en la respuesta de `GET /whatsapp/autoreply`
      (`AutoreplyDefaultsResponse`), igual que `suggested_faqs`
- [x] 3.4 `GET /whatsapp/quick-replies` detrás de `messaging.attend`, devolviendo **sólo** la lista y
      **sólo lo guardado**: `null` → `[]`. Las sugeridas no salen por aquí (design §6) — enseñarle al
      mesero plantillas que el dueño no aprobó es poner palabras en boca del negocio
- [x] 3.5 Pruebas de permisos, las tres: `attend` lee; `attend` sin `manage` **no** guarda; sólo
      `read` **no** lee
- [x] 3.6 Prueba de que leer la lista no emite nada ni toca el estado de ninguna conversación

## 4. Frontend — contrato y estado

- [x] 4.1 Tipo `QuickReply` y `quickReplies` en el contrato de ajustes de `messaging.api.ts`, más el
      cliente de `GET /whatsapp/quick-replies`
- [x] 4.2 Carga en el store del inbox: **una vez por sesión de la pantalla**, no por conversación
      (design). Fallo de carga = sin selector, nunca un error que tape el compositor: no poder ver
      las plantillas no impide responder

## 5. Frontend — editor (quinta sección de `/whatsapp/autoreply`)

- [x] 5.1 `QuickReplySection.vue` con el patrón de `FaqSection`: tarjetas colapsables, alta, baja,
      edición, reordenar con flechas ↑↓ (cero librería nueva, pulgar y teclado)
- [x] 5.2 Contador de caracteres contra `MAX_QUICK_REPLY_CHARS` y aviso al pasarse, antes de guardar
- [x] 5.3 Validación de marcadores en la pantalla, con el mismo mensaje que el backend: quien escribe
      `{link}` tiene que enterarse ahí, no en el 422
- [x] 5.4 Botón de "usar las sugeridas" cuando el tenant está sin configurar. **Rellena el formulario
      y no guarda**: adoptar y marcharse sin guardar deja al tenant como estaba
- [x] 5.5 Texto de ayuda que diga que estas plantillas **no contestan solas** — están en la misma
      pantalla que las FAQs, que sí lo hacen, y esa confusión es el fallo de producto más probable
- [x] 5.6 Montar la sección en `WhatsAppAutoreplyView.vue` con su `dirty` y su guardado
- [x] 5.7 Pruebas de la sección: crear, borrar, reordenar, adoptar sugeridas sin guardar, y que
      `{link}` bloquea el guardado

## 6. Frontend — selector en el compositor

- [x] 6.1 Botón junto al del clip que abre un popover con las plantillas: nombre en mono, texto
      recortado a una línea. `aria-haspopup`, `Escape` cierra y devuelve el foco, clic fuera cierra
- [x] 6.2 Sin plantillas guardadas **no se pinta el botón**: un menú vacío sin explicación es peor
      que ningún menú
- [x] 6.3 Detrás de los gates que el compositor ya tiene: `canAttend`, `isClosed`, `offline`. Cero
      gates nuevos — si el compositor no deja escribir, esto tampoco aparece
- [x] 6.4 Inserción **en el cursor**, con espacio de separación si hace falta, cursor al final de lo
      insertado y foco de vuelta al `textarea`. Nunca reemplaza el borrador: es la regla #1 escrita
      en el propio componente
- [x] 6.5 Pruebas: seleccionar no envía nada; el borrador previo sobrevive; dos plantillas seguidas
      se concatenan; desconectado no hay selector

## 7. Cierre

- [x] 7.1 Documentar la sección en `docs/messaging/` junto al resto del canal, incluida la razón de
      que no haya marcadores (para que no se "arregle" dentro de seis meses)
- [x] 7.2 Puertas verdes: `ruff`, `mypy`, suite de backend, `vitest`, `type-check` y `eslint`
- [x] 7.3 Repasar que el pipeline de entrada no menciona `quick_replies` en ningún sitio
