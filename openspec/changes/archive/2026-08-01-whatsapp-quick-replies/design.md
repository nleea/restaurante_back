## Context

El inbox de WhatsApp ya sabe responder: `MessageComposer.vue` con texto y adjuntos,
`send_reply` / `send_media_reply` detrás. Lo que no tiene es memoria de lo que el negocio contesta
todos los días, así que las mismas cuatro frases se reescriben a mano en cada turno.

El sitio donde ponerlas apareció con las FAQs por palabra clave: `whatsapp_autoreply_settings`, una
fila por tenant, con `faqs` como JSON nullable y toda la maquinaria de leer/validar/guardar ya
montada alrededor del `GET`/`PUT /whatsapp/autoreply`. Este change es en buena medida un calco de
esa forma, y el diseño consiste sobre todo en decidir **qué partes del calco NO copiar**.

La restricción que lo cambia todo: **una respuesta rápida no la manda el sistema**. Las FAQs
tuvieron que traer gates de estado, gate de pedido vivo, emisión única y vocabulario reservado
porque el sistema hablaba solo y un falso positivo era un mensaje bochornoso sin nadie detrás.
Aquí siempre hay alguien detrás —es literalmente el texto que esa persona iba a escribir a mano—,
así que ninguna de esas defensas tiene a qué defenderse.

## Goals / Non-Goals

**Goals:**

- Guardar por tenant una lista ordenada de plantillas `{id, name, text}` y editarla en la pantalla
  de ajustes que ya existe.
- Que quien atiende el inbox las pueda leer e insertar, aunque no pueda administrar nada.
- Que insertar una plantilla no pueda destruir lo que el empleado lleva escrito.
- Que sea imposible guardar una plantilla que se vería rota en el chat del cliente.

**Non-Goals:**

- **Interpolación.** Nada de `{link}`, `{next_opening}`, `{nombre}`. Ver decisión 4.
- **Disparo automático.** Ni por palabra clave ni por estado. Eso es `whatsapp-autoreply` y ya
  existe; duplicarlo aquí sería tener dos motores contestando en el mismo hilo.
- **Plantillas por sucursal o por empleado.** Tenant y punto, como el saludo. Tres listas para tres
  sedes es peor producto que una lista.
- **Adjuntos guardados en la plantilla.** Sólo texto. Un PDF de precios guardado en un ajuste es
  `media-storage`, otro change.
- **Atajos de teclado tipo `/gracias`.** Un parser dentro del compositor es superficie nueva; el
  selector con el pulgar resuelve el 100% del caso y el atajo resolvería el 10% más rápido.

## Decisions

### 1. Columna nueva en la fila de ajustes, no tabla propia

`quick_replies`, JSON nullable, en `whatsapp_autoreply_settings`.

**Por qué:** la fila ya es "cómo habla este negocio por WhatsApp", ya es una por tenant, ya se lee
entera y se escribe entera, y ya tiene el `GET`/`PUT` con su permiso. Una tabla propia costaría
migración + modelo + repositorio + router + vista, y compraría exactamente cero: no hay consulta
que quiera filtrar plantillas, ordenarlas por SQL ni unirlas con nada.

**Contra, y es real:** la tabla se llama `autoreply` y esto no es autoreply. El riesgo no es
técnico sino de lectura —dentro de seis meses alguien asume que las plantillas disparan solas—.
Se mitiga donde se lee, no donde se guarda: capability separada (decisión 2), docstring en la
columna que lo dice con todas las letras, y el texto de ayuda de la sección.

**Alternativa descartada:** tabla `whatsapp_quick_replies` con una fila por plantilla y `position`.
Convierte el reordenar en una transacción de N updates y guardar dos verdades (la posición y el
orden), que es justo el error que `FaqEntry` documenta haber evitado.

### 2. Capability nueva, no una ampliación de `whatsapp-autoreply`

Comparten fila y nada más. `whatsapp-autoreply` es "cuándo y qué contesta el sistema solo", y todos
sus requisitos se leen con ese sujeto. Colgar de ahí unos requisitos cuyo sujeto es una persona
obliga a leer cada uno preguntándose si aplica, que es exactamente cómo se pudre una spec.

### 3. `{id, name, text}` y nada más

Se caen los dos campos de `FaqEntry` que aquí no significan nada:

- **`enabled`**: una FAQ apagada existe pero no dispara. Una plantilla no dispara nunca, así que
  "apagada" sólo puede querer decir "no la enseñes", y para eso ya está borrarla. Un booleano cuyo
  único valor útil es `true` es un booleano que alguien va a poner en `false` esperando otra cosa.
- **`triggers`**: sólo tienen sentido leyendo el mensaje del cliente. Aquí no se lee nada.

El `id` lo acuña la pantalla y el backend sólo garantiza que no se repita, igual que en `FaqEntry`.
El orden de la lista es el orden de presentación; sin campo `position`, por lo mismo que allí.

### 4. Ningún marcador, y se rechaza al guardar

`_reject_unknown(text, frozenset(), where)` — el conjunto permitido es **vacío**, así que cualquier
`{loquesea}` es un marcador desconocido y sale un 422 con el nombre de la plantilla. Se reutiliza
la función que ya valida el saludo y las FAQs; no hay validación nueva que escribir.

**Por qué no interpolar:** el compositor no resuelve plantillas —mete texto en un `textarea`—, así
que un `{nombre}` guardado saldría por WhatsApp con las llaves puestas. Las dos salidas serían
resolver los marcadores en el frontend (necesita la identidad del negocio, el horario de la sede y
el contexto del pedido dentro del compositor: maquinaria nueva de verdad) o resolverlos en un
endpoint al insertar (un round-trip por toque). Ninguna de las dos cabe en "es una lista de textos
en los ajustes". Rechazar al guardar cuesta una línea y convierte un fallo que se descubre en un
chat real en un error que se ve con el dueño mirando la pantalla.

**Consecuencia aceptada:** una plantilla no puede saludar por el nombre del cliente. Se asume:
quien la usa está viendo el nombre en la cabecera del hilo y puede escribirlo.

### 5. Lectura con `attend`, escritura con `manage`

`GET /whatsapp/quick-replies` detrás de `messaging.attend`; el guardado entra por el
`PUT /whatsapp/autoreply` que ya existe, detrás de `messaging.manage`.

**Por qué el endpoint aparte:** el `GET /whatsapp/autoreply` es `manage` y devuelve el saludo, el
mapeo de estados y las FAQs. Un mesero que atiende el chat no tiene `manage` ni debe verlo. Si la
única puerta fuera ésa, la feature la usaría sólo el dueño —que es justo quien no está en el chat
en hora punta—. El endpoint nuevo devuelve **sólo** la lista, así que abrirlo a `attend` no filtra
nada más.

**Por qué no `messaging.read`:** la lista sólo existe para meterla en una respuesta. Quien no puede
responder no tiene nada que hacer con ella, y el compositor entero ya está detrás de `attend`.

### 6. La lectura del inbox devuelve lo guardado; las sugeridas son cosa del editor

`null` → el endpoint del inbox devuelve **lista vacía**. Las sugeridas se ofrecen únicamente en el
editor, con un botón explícito de "usar las sugeridas" que rellena el formulario **sin guardar**.

**Por qué:** enseñarle al mesero unas plantillas que el dueño nunca aprobó es poner palabras en la
boca del negocio. En las FAQs sembrar era el punto peligroso del change y por eso nacían apagadas;
aquí el equivalente exacto de "apagada" es "no está en la lista guardada".

La distinción `null` ≠ `[]` sigue siendo obligatoria, pero por el otro motivo: sin ella, "las borré
todas" y "nunca las configuré" son el mismo valor, y el editor resucitaría las sugeridas en el
siguiente render sobre una decisión explícita del dueño. Es el mismo bug que el `armed` sin fila de
las alertas, ya documentado.

### 7. Insertar en el cursor, nunca reemplazar

El componente ya lleva escrita su regla #1: *"no perder trabajo ajeno"* —el borrador no se limpia ni
cuando falla un envío—. Sustituir el borrador por la plantilla la rompería de la peor forma, porque
el trabajo perdido sería el de un toque atrás.

Concretamente: se inserta en `selectionStart`, se pega un espacio si el carácter anterior no es
espacio, se recoloca el cursor al final de lo insertado y se devuelve el foco al `textarea`. Dos
plantillas seguidas se concatenan, que es el comportamiento que alguien va a probar el primer día.

### 8. Selector: popover propio, sin librería

Un `<button>` con `aria-haspopup` junto al del clip, y una lista de `<button>` con el nombre en
`font-mono` y el texto recortado a una línea. `Escape` cierra, el foco vuelve al disparador, un
clic fuera cierra. Vive detrás de los mismos gates que el resto del compositor (`canAttend`,
`isClosed`, `offline`), y sin plantillas guardadas no se pinta: un menú vacío sin explicación es
peor que ningún menú.

### 9. Topes

`MAX_QUICK_REPLIES = 20`, `MAX_QUICK_REPLY_CHARS = 1000`, nombre ≤ 40. El tope de texto queda muy
por debajo de `MAX_REPLY_CHARS = 4096` a propósito: una plantilla es una frase, no un folleto, y el
compositor puede recibir dos seguidas sin pasarse del límite real de envío. El tope de cantidad es
lo que cabe en un popover sin scroll infinito y con el pulgar.

## Risks / Trade-offs

- **La columna vive en una tabla que se llama `autoreply` →** capability separada, docstring
  explícito en el modelo, y texto de ayuda en la sección que dice que estas plantillas no contestan
  solas. El nombre de la tabla no se toca: renombrarla es una migración con riesgo real a cambio de
  estética.
- **Sin marcadores, la plantilla nunca es del todo la frase final →** aceptado y explícito
  (decisión 4). Si algún día pesa, la salida no es interpolar en el frontend sino un
  `POST /quick-replies/{id}/render` que devuelva el texto resuelto para esa conversación; el
  esquema `{id, name, text}` no lo impide.
- **Dos gerentes editando ajustes a la vez se pisan →** ya pasa hoy con el saludo, el mapeo y las
  FAQs: el `PUT` guarda el documento entero. No se arregla aquí; arreglarlo es un change de
  concurrencia optimista para toda la pantalla.
- **El endpoint nuevo se llama en cada apertura de conversación →** se carga una vez por sesión del
  inbox y se cachea en el store, no por hilo. La lista cambia cuando el dueño la guarda, y ver una
  plantilla vieja durante un turno no rompe nada.
- **Un empleado puede insertar y borrar media plantilla antes de enviar →** es una feature, no un
  riesgo: el mensaje siempre lo firma una persona que lo leyó.

## Migration Plan

1. Migración `0034`: `ALTER TABLE whatsapp_autoreply_settings ADD COLUMN quick_replies JSON NULL`.
   Sin backfill, sin `server_default`: los tenants existentes nacen en `null`, que es exactamente
   "nunca las configuré".
2. Backend y frontend son aditivos —endpoint nuevo, campo opcional en un payload existente,
   componentes nuevos—, así que se pueden desplegar juntos sin ventana.
3. **Rollback**: revertir el código deja la columna con datos y sin lector; nadie la mira. Si hay
   que revertir la migración, se pierde la lista de plantillas y nada más: ningún flujo depende de
   ella, ningún mensaje se deja de mandar.

## Open Questions

Ninguna bloqueante. Dos se resolvieron antes de escribir esto y quedan anotadas por si vuelven:
dónde vive la configuración (decisión 1) y qué pasa al tocar una plantilla (decisión 7).
