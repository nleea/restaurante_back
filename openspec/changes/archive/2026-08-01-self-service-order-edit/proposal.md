## Why

Un cliente que ya pidió se acuerda de algo treinta segundos después — que quería la hamburguesa
sin lechuga, que se le olvidó el queso extra, que quiere otra para su hermano. Hoy eso sólo se
resuelve escribiendo por WhatsApp y esperando a que alguien lo lea, lo entienda y lo teclee.

La respuesta obvia era darle esa capacidad al asistente. **Se descartó a propósito**, y el motivo
es lo que da forma a este cambio: para que un LLM edite un pedido tendría que inventarse un
precio (`add_item` recibe el precio de quien llama), reescribir una nota de texto libre sin
perder lo que ya decía, sostener una confirmación entre turnos y ganarle una carrera a la
cocina. Cuatro riesgos nuevos para un problema que no los necesita.

En su lugar, el cliente edita **su propio pedido en una vista**, con el catálogo delante y los
precios del read-model. El asistente vuelve a hacer lo único que hace bien —interpretar— y
decide a qué puerta mandar cada petición. `assistant-core` sigue siendo de sólo-lectura.

Como efecto colateral, la vista sirve a cualquiera que haya pedido por la carta, escriba o no
por WhatsApp.

## What Changes

- **Un enlace por pedido.** Se acuña un token **por pedido**, no se reutiliza el del chat: el
  del chat identifica al contacto, así que reenviarlo daría acceso a *todos* sus pedidos. Un
  token por pedido acota el daño de un enlace compartido a ese pedido, y cubre al cliente web
  que nunca escribió por WhatsApp.
- **El total nunca baja.** Es la invariante que sustituye a una lista de verbos permitidos, y se
  comprueba **sobre el pedido resultante**, no paso a paso — un cambio de producto es "quitar y
  poner", y validado por pasos el intermedio siempre bajaría. De ella se deriva solo que cambiar
  una gaseosa por otra del mismo precio valga y cambiarla por agua no.
- **Se puede añadir, subir cantidad, añadir adiciones y editar notas.** Quitar, bajar cantidad y
  cancelar **no**: eso lo resuelve una persona.
- **Cambiar un producto por otro igual o más caro** se permite mientras el pedido no tenga pago
  registrado.
- **Con pago registrado, las líneas existentes sólo crecen.** Se les pueden añadir adiciones y
  cantidad, pero no cambian de producto: la identidad de una línea ya pagada no se reescribe, o
  "yo pagué por una gaseosa negra" deja de tener respuesta. Lo añadido entra como **líneas
  nuevas**, de modo que lo pagado queda congelado y lo nuevo se ve aparte.
- **Dos ventanas, no una.** Por ítem: sólo si ninguna de sus estaciones pasó de `pending`. Por
  pedido: se apaga cuando **la comida deja de estar al alcance** — un domicilio al pasar a
  `in_transit`, y un pedido para recoger o de mesa al quedar `ready`. La línea es física: entre
  un pedido listo y una moto que ya salió, la bolsa sigue en el pase y un cocinero todavía puede
  hacer una cosa más.
- **Lo añadido se envía solo a cocina.** `add_item` deja los ítems sin enrutar a propósito (el
  personal compone y envía); por esta vía no hay personal componiendo, y un ítem que se factura
  sin cocinarse es peor que no haberlo dejado añadir.
- **La diferencia a pagar se dice con todas las letras.** Añadir sobre un pedido pagado lo deja
  debiendo otra vez; si la vista no lo enseña, el domiciliario llega a cobrar una plata que el
  cliente no esperaba.
- **El asistente enruta, no escribe.** Añadir/notas/cambiar → el enlace de ese pedido.
  Quitar/cancelar/devolver → una persona. Mandar al enlace a quien quiere quitar algo es peor que
  no mandarlo: llega a una pantalla que no hace lo que pidió.
- El horario apaga al **asistente**, no a la vista: la vista depende del estado del pedido. A las
  11 de la noche, con el pedido abierto y sin confirmar, corregirlo no molesta a nadie.

## Capabilities

### New Capabilities
- `self-service-order-edit`: leer y editar el propio pedido desde un enlace con token — la
  invariante del total, las dos ventanas (ítem y pedido), la regla de las líneas pagadas y el
  auto-envío a cocina de lo añadido.

### Modified Capabilities
- `storefront-public-api`: gana el token por pedido y los endpoints públicos de lectura y
  edición, atados a ese token; hoy sólo resuelve el token del contacto y crea pedidos.
- `frontend-storefront`: gana la vista "mi pedido", con las casillas de "sin …" ya marcadas, las
  adiciones, la cantidad y el delta a pagar visible.
- `assistant-core`: el asistente aprende a enrutar entre el enlace y una persona. **No** deja de
  ser de sólo-lectura: el requisito sigue vigente y este cambio lo reafirma.

## Impact

- **Backend**: `storefront` gana lectura y edición pública por token; `orders` expone la
  composición de una edición bajo la invariante (sin nuevos verbos de dominio salvo el cambio de
  variante de una línea, que hoy no existe); enrutado a cocina de lo añadido cuando el pedido ya
  está en cocina.
- **Nuevo token**: por pedido, con vida propia. Es una URL-capacidad: quien la tenga edita ese
  pedido, así que su caducidad es parte del diseño.
- **Frontend**: nueva vista pública bajo `/store`; reutiliza el widget de exclusiones del
  checkout.
- **Cocina**: puede ver aparecer un ticket nuevo a mitad de servicio. El KDS ya es en vivo.
- **Caja**: un pedido pagado puede volver a quedar debiendo. Cerrar ya exige estar saldado, así
  que la regla existente cubre el caso; lo que cambia es que ahora ocurre más a menudo.
- **No rompe nada**: sin token acuñado no hay vista, y el asistente sigue sin escribir.
