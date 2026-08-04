## Why

Un domicilio hoy no tiene principio ni final. **No tiene principio**: el registro de entrega
nace al abrir el pedido (para capturar la dirección y geocodificar el pin), y nadie mira la
cocina antes de asignarlo — se puede despachar y marcar como entregado un pedido que la cocina
nunca vio. Ya pasó en producción. **No tiene final**: `mark_delivered` cambia un estado y nada
más; no registra pago ni cierra la comanda, así que un domicilio entregado sigue apareciendo en
Salón esperando cobro que ya nadie va a hacer.

Entre medias falta la pieza que hace que el dinero cuadre: el efectivo lo cobra el domiciliario
en la puerta, y el prepago (transferencia/Nequi/tarjeta) alguien lo verifica antes de cocinar.
Ninguno de los dos momentos existe en el sistema.

La causa del primer problema es un choque de dos decisiones tomadas por separado: la vieja
creaba el registro de entrega al llegar a `ready` (lo que impedía despachar comida cruda), la
nueva lo crea al abrir el pedido (lo que hace posible el pin). Ganó la nueva, con razón — pero
nadie ocupó el puesto que dejó vacante la vieja.

## What Changes

- **Asignar exige cocina lista.** Una entrega solo se puede asignar a un despacho cuando su
  pedido tiene `kitchen_state = ready`. Se deriva del pedido, sin estado nuevo en la entrega:
  duplicar ese dato sería inventar una segunda verdad. La regla es **la misma para efectivo y
  para prepago** — el método de pago decide cuándo entra la plata, nunca cuándo sale la comida.
- **Las entregas no listas se ven, pero no se tocan.** Despacho las lista bloqueadas con el
  motivo, en vez de ocultarlas: al despachador le sirve saber qué viene.
- **El prepago se verifica antes de cocinar.** En un pedido con método distinto de efectivo,
  enviar a cocina exige que el pago esté verificado. Verificar es un solo gesto: quien atiende
  mira el comprobante o el Nequi, confirma, y eso **registra el pago y dispara la cocina**.
- **Resolver una entrega cierra la comanda, en los dos desenlaces.** Entregada cierra bajo las
  reglas de siempre. **No entregada también cierra**, absorbiendo lo impagado como pérdida sin
  fiárselo al cliente: cerrar es el único momento en que se descuenta inventario, y esa comida se
  cocinó igual. Dejarla abierta haría que la despensa reportara stock que ya no existe.
- **En efectivo, cobrar y cerrar son un solo gesto.** La pantalla del domiciliario muestra cuánto
  debe recibir y un botón que confirma el dinero y cierra la comanda a la vez: o pasan las dos
  cosas, o no pasa ninguna.
- **Devoluciones** (nuevo). Un pedido prepagado que no se entregó genera una obligación de
  devolver, con quien la autorizó y por qué. Al confirmarla se crea el movimiento de caja de
  salida **con el método original** — nunca efectivo: esa plata jamás estuvo en el cajón, y
  registrarla como efectivo rompería el arqueo justo al intentar cuadrarlo. Una devolución
  pendiente **no** traba el cierre de caja.
- **BREAKING** — **La caja no cierra con domicilios sin resolver.** Reemplaza el requirement
  actual `Force-close is never blocked by pending items`. Resuelto significa `delivered` o
  `not_delivered`; el conteo ya se calcula así en el código, es el texto del spec el que dice
  impreciso "not in a delivered state".
- **Una entrega se puede marcar "no entregada" desde cualquier estado no terminal.** Hoy exige
  `in_transit`, así que un pedido que se cocinó y nunca salió no puede cerrarse nunca. Sin esto,
  bloquear la caja la dejaría trabada sin salida. Los motivos existentes ya sirven
  (`Cliente canceló`, `Otro`).

Fuera de alcance: pagos parciales o mixtos en la puerta, devoluciones parciales, reprogramar una
entrega fallida como nuevo intento (hoy se resuelve creando otro pedido), e integración con
pasarelas — verificar un pago es un humano mirando un comprobante, no una API.

## Capabilities

### New Capabilities
- `delivery-settlement`: el cierre económico de un domicilio — verificación de pago como puerta
  a la cocina, cobro en efectivo en la puerta, y el cierre automático de la comanda al entregar.
- `order-refunds`: la obligación de devolver dinero de un pedido prepagado no entregado — cómo
  nace, cómo se lista y cómo se salda contra la caja con su método original.
- `frontend-delivery-settlement`: las pantallas del flujo — entregas bloqueadas en Despacho, el
  "confirmar y cerrar" del domiciliario, la verificación de pago en Salón, el cierre de caja
  bloqueado y la lista de devoluciones pendientes.

### Modified Capabilities
- `delivery-management`: asignar exige que la cocina esté lista; una entrega se puede marcar no
  entregada desde cualquier estado no terminal, no solo desde `in_transit`.
- `cash-management`: cerrar una sesión se bloquea mientras haya domicilios sin resolver
  (reemplaza `Force-close is never blocked by pending items`), y se precisa qué cuenta como
  sin resolver.
- `kitchen-management`: enrutar a la cocina un pedido con método de pago prepagado exige que su
  pago esté verificado.
- `order-management`: se añade un cierre "write-off" que absorbe el saldo impagado como pérdida
  del negocio en vez de fiárselo al cliente, alcanzable **solo** al resolver una entrega no
  entregada.

## Impact

- **Backend**: `delivery` (gate de asignación en `assign_delivery`, `mark_delivered` desde
  cualquier estado no terminal y cerrando el pedido), `orders` (verificación de pago,
  cierre disparado desde la entrega), `cash` (`close_session` bloqueante), `reports`
  (el conteo pendiente pasa de informativo a vinculante) y un módulo/tabla nueva para
  devoluciones. Migración nueva.
- **Un cierre de pedido deja de ser solo del cajero.** `close_order` pasa a tener un segundo
  disparador (la entrega) y un tercer desenlace para el saldo impagado: además de rechazar o
  fiar, puede absorberlo como pérdida. Ese modo es alcanzable **solo** desde una entrega no
  entregada; para cualquier otro cierre la regla de hoy sigue igual de estricta. El descuento de
  inventario por recetas no cambia en ningún caso.
- **Frontend**: Despacho (bloqueadas), Domiciliario (cobrar y cerrar), Salón (verificar pago),
  Caja (cierre bloqueado + devoluciones pendientes).
- **Operativo**: cambia el orden del turno. Hoy el cajero cierra cuando quiere; a partir de
  ahora cerrar exige que cada domicilio tenga un desenlace escrito. Es más trabajo por turno y
  es deliberado: ese es justo el dato que hoy se pierde.
- **No rompe datos**: no hay migración de estados; lo que cambia son las reglas de transición.
