## Why

De las tres cosas del brief del inbox que quedaron sin construir —el ✓✓ de entregado/leído, el
audio y las respuestas rápidas—, ésta es la única que no está bloqueada por nada externo. El ✓✓
espera a que escuchemos `MESSAGES_UPDATE` del puente; el audio espera una decisión de
almacenamiento. Las respuestas rápidas no esperan nada: **no había dónde guardar las plantillas**,
y desde las FAQs sí lo hay.

El problema que resuelven es el que se ve en cualquier hora punta. La misma frase —"Ya salió tu
pedido, llega en unos 20 minutos", "Sí, hacemos domicilio a todo el centro", los datos de
Nequi— se reescribe a mano veinte veces al día, con una errata distinta cada vez. Es trabajo
mecánico dentro del único momento del día en que nadie tiene manos libres.

La distinción que hace este change barato y sin riesgo, y conviene decirla de entrada: **una
respuesta rápida no responde nada**. No es un motor más del pipeline de entrada, no lee el
mensaje del cliente, no decide. Es texto que una persona mete en el compositor antes de pulsar
enviar. Toda la maquinaria de las FAQs —gates de estado, pedido vivo, emisión única, vocabulario
reservado— existe porque ahí el sistema hablaba solo. Aquí no habla nadie que no sea un empleado,
así que nada de eso hace falta.

## What Changes

- **Lista de plantillas por tenant**: `[{id, name, text}]`. Sin `enabled` y sin `triggers` —los dos
  campos de una FAQ que sólo tienen sentido cuando algo dispara sola. Una plantilla existe en la
  lista o no existe; el orden de la lista es el orden en que se ven.
- **Almacenamiento JSON nullable** en la fila de ajustes que ya existe, con la misma regla que
  `faqs` y por la misma razón: `null` = este tenant nunca las tocó → se le ofrecen las sugeridas;
  `[]` = decidió que ninguna. Sin esa distinción, "las borré todas" y "nunca las configuré" son
  indistinguibles y una plantilla borrada **resucita** en la siguiente lectura.
- **Rellenan, no envían.** Tocar una plantilla mete su texto en el compositor y deja el foco
  dentro. El empleado la edita si quiere y pulsa enviar él. Un toque equivocado no le llega a
  nadie, que es la propiedad que permite poner el botón al lado del de enviar.
- **Se inserta en el cursor y nunca pisa lo escrito.** El borrador del compositor es trabajo de una
  persona; la regla #1 de ese componente ya es "no perder trabajo ajeno" y esto no la rompe.
- **Sin marcadores.** `{link}`, `{next_opening}` y compañía se **rechazan al guardar** (422). No es
  pereza: el compositor no resuelve plantillas, así que un `{nombre}` guardado saldría por WhatsApp
  tal cual, con las llaves. Mejor no dejar escribirlo que dejar que se descubra en un chat real.
- **Lectura con `messaging.attend`, escritura con `messaging.manage`.** El editor vive detrás de
  `manage` como el resto de los ajustes, pero el inbox lo atiende gente que no administra nada: si
  la única forma de leer la lista fuera el `GET /autoreply`, la feature sólo la vería el dueño.
  Endpoint de lectura propio, y sólo devuelve las plantillas.
- **Quinta sección en `/whatsapp/autoreply`**, con el patrón de `FaqSection`: tarjetas colapsables,
  reordenar con flechas ↑↓, contador de caracteres, y un botón para sembrar las sugeridas.
- **Selector en el compositor**: un botón junto al del clip abre la lista; teclado y `Escape`
  cierran; con el número desconectado o sin permiso de atender, no aparece —igual que el resto del
  compositor.

## Capabilities

### New Capabilities

- `whatsapp-quick-replies`: la lista de plantillas por tenant —su forma, su validación al guardar,
  la semilla de sugeridas y el camino de lectura para quien atiende—. Capability nueva y **no** una
  ampliación de `whatsapp-autoreply` a propósito: comparten fila en la base de datos y nada más.
  `whatsapp-autoreply` es "cuándo y qué contesta el sistema solo"; aquí el sistema no contesta.
  Meterlas ahí obligaría a leer cada requisito de esa capability preguntándose si aplica al caso
  en que no hay automatismo.

### Modified Capabilities

- `frontend-whatsapp-settings`: gana la quinta sección del editor, su validación de longitud y de
  marcadores prohibidos, y el sembrado de sugeridas.
- `frontend-whatsapp-inbox`: el compositor gana el selector de plantillas y la regla de inserción
  en el cursor sin pisar el borrador.

## Impact

- **Backend `messaging`**: entidad `QuickReply`, funciones puras de validación (longitud, tope de
  plantillas, ids repetidos, marcadores prohibidos) en el mismo criterio que `templates.py` y
  `faq.py` —sin base, sin red, sin reloj—; columna nueva en el modelo y el repositorio; un caso de
  uso de lectura y otro de guardado; dos endpoints (`GET /whatsapp/quick-replies` con `attend`,
  y el campo nuevo dentro del `PUT /whatsapp/autoreply` que ya existe).
- **Migración 0034**: columna JSON nullable. Los tenants existentes nacen en `null` y ven las
  sugeridas en el editor. **A diferencia de las FAQs, sembrar no cambia el comportamiento de
  nadie**: una plantilla que nadie toca no manda nada. Es la razón de que aquí no hagan falta ni
  el `enabled` ni el "nacen apagadas" que allí eran obligatorios.
- **Frontend**: `QuickReplySection.vue` en `components/messaging/autoreply/`, selector en
  `MessageComposer.vue`, tipos y cliente en `messaging.api.ts`, y la acción de carga en el store
  del inbox. Sin librerías nuevas.
- **Sin permiso nuevo**: `messaging.attend` y `messaging.manage` ya están sembrados, así que no
  hace falta volver a correr `scripts.seed`.
- **Volumen de salida**: no sube. No hay ningún mensaje que salga sin que una persona lo mande.
- **No rompe nada**: columna nueva nullable, endpoint nuevo, campo opcional en un payload que ya
  se guarda entero. Un tenant que no abra la sección no nota el change.
