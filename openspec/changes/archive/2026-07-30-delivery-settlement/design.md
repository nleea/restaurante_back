## Context

Cuatro módulos se tocan aquí y ninguno es dueño del problema: `delivery` sabe si llegó,
`kitchen` sabe si está cocinado, `orders` sabe si está pagado y `cash` sabe si el turno cerró.
Hoy cada uno hace su parte bien y **nadie conecta las cuatro**.

El estado actual, verificado en código:

- `assign_delivery` (`manage_delivery.py:498`) valida sucursal, estado del despacho y estado de
  la entrega. No mira la cocina.
- `mark_delivered` (`:546`) cambia `delivery_status` y sella `delivered_at`. No toca pagos ni
  cierra nada. Además exige `in_transit`, así que una entrega que nunca salió no puede
  terminarse.
- `close_order` (`manage_orders.py:497`) ya exige pago completo o fiado y descuenta inventario
  por recetas. Está bien; simplemente nadie lo llama desde la entrega.
- `register_payment` (`manage_payments.py:40`) exige sesión de caja abierta y crea
  **atómicamente** un `cash_movement` gemelo (`in`/`sale`) que lleva el método
  (`repositories.py:647`).
- `cash_totals` (`cash/infrastructure/repositories.py:196`) filtra `method == cash`: el arqueo
  físico solo cuenta efectivo.
- El conteo de domicilios pendientes ya excluye los terminales:
  `delivery_status.notin_(("delivered", "not_delivered"))` (`reports/…/repositories.py:107`).
  El código ya trata `not_delivered` como resuelto; el texto del spec de caja es el impreciso.
- `Order.kitchen_state` (`none | in_kitchen | ready`) ya se deriva de los tickets y se persiste
  sola (`kitchen/…/manage_kitchen.py:61`). Está calculada y guardada — nadie la consulta.
- Los ítems nacen *pending*; enviar a cocina es un gesto explícito
  (`POST /kitchen/orders/{order_id}/route`).

Dos restricciones vinculantes del proyecto enmarcan todo: la caja abierta es la frontera del
turno operativo (sin caja no hay pedidos), y `close_order` es el único sitio donde se descuenta
inventario.

## Goals / Non-Goals

**Goals:**
- Que sea imposible despachar o entregar algo que la cocina no ha terminado.
- Que un domicilio entregado deje de aparecer en Salón pidiendo cobro.
- Que el efectivo que cobra el domiciliario entre en la caja correcta sin que nadie lo decida.
- Que cada domicilio tenga un desenlace escrito antes de cerrar el turno.
- Que devolver dinero deje rastro de quién lo autorizó.

**Non-Goals:**
- Pagos parciales o mixtos en la puerta (paga todo o no se entrega).
- Devoluciones parciales.
- Reprogramar una entrega fallida como segundo intento — hoy es un pedido nuevo.
- Integrar pasarelas de pago: verificar es un humano mirando un comprobante.
- Cambiar cómo se calcula el arqueo o el Reporte Z.

## Decisions

**1. El gate de cocina se deriva de `Order.kitchen_state`; la entrega no gana un estado nuevo.**

```
   ┌──────────────┐   tickets     ┌──────────────────┐   se consulta   ┌──────────────┐
   │   kitchen    │──────────────▶│Order.kitchen_state│───────────────▶│assign_delivery│
   │   tickets    │  (ya existe)  │  none/in_kitchen/ │   (nuevo)      │    gate       │
   └──────────────┘               │      ready        │                └──────────────┘
                                  └──────────────────┘
```

*Alternativa considerada:* un `delivery_status = awaiting_kitchen` previo a `pending`. Rechazada:
sería el mismo hecho guardado en dos sitios, con su clásico problema de desincronización — una
entrega marcada "esperando cocina" cuando la cocina ya terminó es exactamente el bug que
estamos arreglando, reintroducido por otra puerta. Derivar cuesta una columna más en una lectura
que ya hace un batch sobre `orders`.

**2. La misma regla para efectivo y prepago.** El método de pago decide **cuándo entra la
plata**, nunca **cuándo sale la comida**. Un solo gate, sin ramas por método.

**3. Verificar el pago es un gesto, no dos.** En un pedido prepagado, el "OK, el comprobante
está bien" registra el pago **y** enruta a cocina en la misma operación.
*Alternativa considerada:* verificar y enviar por separado. Rechazada: son el mismo momento
mental para quien atiende, y separarlos crea el estado "verificado pero sin cocinar" que nadie
mira y en el que los pedidos se quedan dormidos.

**4. La entrega cierra el pedido llamando a `close_order`, no replicando su lógica.** Sus
invariantes son load-bearing (pago completo o fiado, descuento de inventario por recetas) y
deben valer igual venga el cierre de donde venga. En efectivo, el cobro y el cierre son una sola
operación: registrar el pago y cerrar, o no hacer ninguna de las dos.

```
  efectivo:  [Confirmar $18.500 y cerrar] ──▶ register_payment(cash) ──▶ close_order
                                                     └─ si falla, no se cierra ─┘
  prepago:   [Entregado] ─────────────────────────────────────────────▶ close_order
                                          (ya pagado al verificar)
```

**5. La devolución lleva el método original, nunca efectivo.** Un pago por transferencia crea su
movimiento con `method=transfer`, y el arqueo lo ignora porque solo mira `cash`. Devolverlo como
salida en efectivo haría que el sistema esperara menos plata en el cajón de la que hay: rompería
el arqueo justo al intentar cuadrarlo. Con el método original, el libro de caja registra la
salida y el cajón ni se entera — que es la verdad.

*Simetría que confirma el modelo:* el efectivo nunca genera devoluciones. Si el cliente paga al
recibir y no recibió, no pagó. Solo lo prepagado se devuelve, y lo prepagado nunca tocó el cajón.

**6. La devolución es un registro propio con estado, no un movimiento derivado.**
*Alternativa considerada:* derivarla (pendiente = entrega no entregada ∧ pagada ∧ sin movimiento
de salida), sin tabla nueva. Rechazada pese a ser más simple: es dinero saliendo del negocio, y
"quién autorizó esta devolución" es la pregunta que se hace un dueño el día que aparece una que
nadie recuerda. Derivar tampoco permite decir "esta no se devuelve, se arregló de otra forma"
sin que quede colgada para siempre.

*También rechazado:* reutilizar `customer_credits`. Está definido como deuda **del cliente hacia
nosotros**, con su tabla de abonos; un negativo ahí envenenaría todo "cuánto me deben".

El movimiento de caja se crea **al confirmar**, no al nacer la obligación: hasta que alguien no
hace el Nequi, la plata no ha salido.

**7. La caja bloquea, sin válvula de escape — porque siempre hay una salida honesta.**
Bloquear con `pending | assigned | in_transit`. La salida no es un "cerrar de todos modos": es
resolver la entrega diciendo qué pasó. Para que eso sea siempre posible hace falta la decisión 8.

*Alternativa considerada:* permitir forzar el cierre marcándolo como incidente (`incident` /
`incident_note` ya existen en `close_session`). Rechazada porque compite con la acción correcta:
teniendo un botón de forzar, a las 11pm nadie va a ir a resolver tres entregas. Y el motivo
queda mejor guardado en el pedido que en una nota suelta del cierre.

**8. "No entregado" desde cualquier estado no terminal.** Hoy exige `in_transit`, así que un
pedido cocinado que nunca salió es inmortal. Sin esto, la decisión 7 traba el turno para siempre.
Los motivos existentes ya cubren el caso (`Cliente canceló`, `Otro`).

**9. Una devolución pendiente no traba el cierre.** La plata está en el banco, no en el cajón: el
arqueo cuadra igual. Trabar el turno por un Nequi que alguien hará mañana es el bloqueo que
obliga a inventar atajos. Queda como deuda visible y persistente, no como candado.

## Risks / Trade-offs

- **Cerrar caja pasa a costar trabajo.** [Un turno con seis domicilios sin marcar no cierra hasta
  que alguien los resuelva uno por uno] → Es deliberado: ese es justo el dato que hoy se pierde.
  Mitigado con la lista accionable en el propio diálogo de cierre y con `delivery.assign`
  pudiendo resolver en nombre del domiciliario que se quedó sin batería.
- **El gate de cocina puede parecer un bug el primer día.** [Una entrega visible que no se deja
  asignar se lee como "la app está rota"] → Se muestra bloqueada **con el motivo**, no
  deshabilitada en silencio.
- **Un pedido prepagado sin verificar no llega a la cocina.** [Si nadie mira Salón, la comida
  nunca se cocina y el cliente ya pagó] → El pedido queda visible como "esperando verificación";
  la alerta proactiva es materia del change `alert-notifications`.
- **`close_order` gana un segundo disparador.** [Dos caminos hacia el mismo cierre pueden divergir]
  → Mitigado llamando al mismo use case, no replicando la lógica. Un cierre desde la entrega y uno
  desde Salón deben ser indistinguibles en los datos.
- **La devolución no sale sola.** [El sistema registra la obligación, pero el dinero lo mueve un
  humano por Nequi; si nadie lo hace, el cliente no ve un peso] → Fuera de alcance resolverlo:
  aquí solo se garantiza que la deuda no se pierda de vista.
- **Efectivo cobrado y no confirmado.** [El domiciliario cobra, no confirma en la app, y se va]
  → La caja no cierra, que es exactamente la señal que se quiere. El riesgo residual es que
  alguien lo resuelva como "no entregado" para poder cerrar; el rastro queda, y detectarlo es
  materia de reportes, no de este change.

## Migration Plan

Sin migración de datos: no cambian los estados existentes, cambian las reglas de transición.

- Tabla nueva para devoluciones (`pending | done | cancelled`, con empleado, motivo y el pedido
  de origen). Migración `00XX`, siguiente número libre.
- Los pedidos ya abiertos al desplegar quedan sujetos a las reglas nuevas de inmediato. El caso
  incómodo es un domicilio en vuelo en ese momento: cierra bien porque `mark_delivered` sigue
  funcionando desde `in_transit`.
- Un turno abierto en el momento del despliegue puede encontrarse con el cierre bloqueado por
  entregas viejas sin resolver. Es la primera vez y se resuelve marcándolas; conviene desplegar
  con la caja cerrada.
- Rollback: revertir el código restaura el comportamiento anterior sin tocar datos. La tabla de
  devoluciones queda huérfana pero inofensiva.

## Open Questions

- **¿Quién puede verificar un pago?** ¿Basta `orders.pay`, o merece permiso propio? Verificar
  mueve dinero real a los ojos del sistema (crea el `order_payment`), así que reusar `orders.pay`
  parece correcto — pero hay que confirmarlo antes de escribir el gate.
- **¿Qué permiso confirma una devolución?** `cash.move` encaja (crea un movimiento de salida),
  pero autorizar una devolución es más que registrar un movimiento. Podría querer `finance.manage`.
- **¿El pedido de un domicilio no entregado se cancela o queda cerrado sin pago?** Hoy quedaría
  abierto para siempre, que tampoco sirve. Afecta a inventario: `close_order` descuenta recetas, y
  la comida de un pedido que volvió a la tienda sí se consumió. Probablemente cerrarlo con fiado
  a nombre del cliente no es la respuesta; hay que decidirlo antes de implementar la parte de
  devoluciones.
