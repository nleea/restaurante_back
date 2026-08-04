## Context

Una comanda a domicilio nace con su entrega: `orders` crea la fila en `order_deliveries` en cuanto
se toma el pedido. Cancelarla llama a `_free_table` y no toca la entrega, así que la fila queda en
`pending` con su comanda muerta detrás. Nadie puede resolverla por el camino normal —asignar exige
que la cocina esté `ready`, y una comanda cancelada nunca lo estará— y `cash.unresolved_deliveries`
la cuenta como pendiente sin mirar `orders.status`, de modo que **la caja de ese turno no cierra**.

Existe una salida: `mark_delivered(delivered=False)` se acepta desde cualquier estado no terminal,
precisamente para que ninguna entrega sea inmortal. Pero es mentira —la comanda se canceló, no se
intentó entregar— y el tablero, mientras tanto, dice "Todavía no ha entrado a cocina", que manda al
operador a esperar algo que no va a pasar.

En paralelo, el bloque de verificación de un prepago en Salón ofrece "Buscarlo en WhatsApp" bajo la
condición `!pendingClaims.length`. El supuesto era: sin declaración, el comprobante debe estar en el
chat. La página de pago del domicilio (`/payment/delivery/:token`) rompió ese supuesto: ofrece
explícitamente "O mándalo por WhatsApp", el cliente toma esa ruta —la que de verdad usa la gente,
porque el banco ofrece compartir a WhatsApp justo al terminar— y pulsa "Ya pagué", lo que crea una
declaración **sin** `proof_url`. El atajo se esconde justo en el único caso en que era necesario.

## Goals / Non-Goals

**Goals:**

- Que cancelar una comanda no deje nunca una entrega sin desenlace.
- Que el desenlace diga la verdad: una cancelación no es una entrega fallida.
- Que las dos huérfanas existentes queden resueltas sin tocar entregas con desenlace real.
- Que el operador llegue al chat cuando —y sólo cuando— no hay comprobante que mirar.

**Non-Goals:**

- Cambiar quién puede cancelar una comanda, ni cuándo.
- Reabrir una entrega ya resuelta.
- Automatizar la lectura del comprobante en el chat: reclamarlo sigue siendo un acto de una persona.
- Cambiar el flujo de cotización o el enlace de pago.

## Decisions

### `cancelled` es un estado terminal nuevo, no un `not_delivered` disfrazado

Reutilizar `not_delivered` con motivo "Comanda cancelada" no costaría nada y desbloquearía la caja
igual. Se descarta porque `not_delivered` **lo leen los reportes**: mezclar cancelaciones con
entregas fallidas corrompe la única métrica que le importa a la operación de domicilios —cuántas
veces salimos y no logramos entregar—. Una comanda cancelada nunca salió; contarla ahí sería
inventar un fracaso que no ocurrió.

El coste es real y hay que asumirlo: el estado nuevo obliga a repasar cada sitio que enumera los
terminales, en los dos lados.

### Cerrar NO es cancelar, y la entrega se queda

Cerrar una comanda significa que está pagada y **sigue** su camino: cocina y de ahí a despacho.
No es que se haya acabado. Su entrega está precisamente en `pending` esperando que la asignen a
un domiciliario — que es el mismo estado que la liberación consume.

Así que cerrar no toca la entrega. Soltarla ahí sacaría del tablero un pedido ya cobrado y nadie
lo llevaría. La entrega sobrevive al cierre y la resuelve quien sale con ella.

Sólo cancelar libera, porque sólo ahí la comanda deja de existir.

### Sólo se cancela la entrega que nunca salió

`cancel_order` sólo exige que la comanda esté **abierta**, y una comanda con su domicilio ya en la
calle sigue abierta. Así que se puede cancelar algo que un domiciliario lleva encima.

La regla: la entrega se auto-cancela **sólo desde `pending`**. Desde `assigned` o `in_transit` el
desenlace le pertenece a quien salió con la comida, y sigue siendo `not_delivered` con su motivo —
que es exactamente lo que pasó. Cancelar en silencio una entrega que ya iba de camino le borraría
la parada al domiciliario del móvil sin decirle por qué.

Alternativa descartada: prohibir cancelar una comanda con entrega despachada. Es más limpio en el
papel y peor en el mostrador — a veces el cliente cancela justo cuando el domiciliario arranca, y
negar la cancelación no cambia ese hecho.

### La liberación viaja por el puerto que ya existe

`orders` ya habla con `delivery` a través de `DeliveryDispatch` (hoy sólo
`ensure_delivery_for_order`). El puerto gana un verbo para soltar la entrega, y el adaptador
concreto se sigue cableando en el composition root. Así la dependencia sigue yendo en un solo
sentido y cancelar una comanda funciona igual en un despliegue sin domicilios.

Se prefiere a un evento: los eventos de este sistema son un timbre best-effort para refrescar
pantallas, y esto decide si una caja puede cerrar.

### El predicado "sin resolver" se escribe una vez

Hoy la lista de estados terminales está copiada en tres sitios: `D_TERMINAL` en delivery, el
`notin_` de `cash.unresolved_deliveries` y el mismo `notin_` en el histórico de sesión de reports.
Añadir un estado sin tocar los tres deja el bloqueo puesto y el síntoma reaparece idéntico, lo que
lo hace un bug caro de diagnosticar dos veces.

La decisión es derivar los tres del mismo sitio en vez de añadir un tercer literal. Cuál es ese
sitio se resuelve al implementar; lo que no se acepta es dejar tres copias.

### El atajo al chat se decide por "¿hay algo que mirar?", no por "¿hay declaración?"

La condición pasa a ser: mostrar cuando **ninguna** declaración pendiente trae `proof_url` y la
comanda tiene contacto de WhatsApp. Una declaración sin comprobante es precisamente la señal de que
el dinero se declaró y la evidencia está en otro sitio.

Con un comprobante adjunto el atajo no aparece: la imagen ya está delante y el enlace sería ruido.
El destino no cambia —la bandeja con `?contact=`, donde ya existe "usar un archivo como
comprobante"— porque ahí la imagen está guardada, funciona en cualquier dispositivo y no exige la
sesión de WhatsApp de la sede en ese navegador.

### Una entrega cancelada desaparece del tablero

El tablero de despacho es una lista de trabajo: lo que está ahí es algo que alguien tiene que
hacer. Una entrega cancelada no le pide nada a nadie, así que quedarse —aunque fuera en gris— la
convertiría en ruido que hay que aprender a ignorar, y un tablero que se ignora a trozos se ignora
entero.

Se pierde poder explicar de un vistazo por qué bajó el número de domicilios del turno. Se acepta:
esa pregunta es de reportes, y la entrega sigue existiendo con su estado para quien la busque.

### Las huérfanas se limpian con una migración de datos acotada

Sólo las filas que cumplan las tres condiciones a la vez: comanda **cancelada**, entrega en
`pending`, y sin `delivered_at`. Nada que haya tenido un desenlace real se toca. La migración es
idempotente y su `downgrade` no revive nada: devolver esas filas a `pending` reintroduciría el
bloqueo a propósito.

## Risks / Trade-offs

- [Un lugar que enumere los terminales se queda sin actualizar] → derivar los tres del mismo sitio
  en vez de copiar el literal; una prueba que recorra los consumidores y falle si alguno discrepa.
- [La vista del domiciliario o el tablero pintan un estado que no conocen] → el estado nuevo entra
  en las etiquetas de las dos superficies; sin eso aparece el literal crudo en pantalla.
- [Cancelar una comanda cuya entrega ya salió] → no se toca la entrega; el desenlace sigue siendo
  del domiciliario, y eso queda cubierto por un escenario propio.
- [La migración toca una entrega que sí tuvo desenlace] → las tres condiciones son conjuntas y
  `delivered_at` nulo es la garantía de que nadie la resolvió.
- [El atajo al chat aparece cuando el pedido no vino de WhatsApp] → sigue exigiendo contacto
  vinculado; sin él no hay conversación a la que ir.

## Migration Plan

1. Añadir el estado terminal y unificar el predicado, sin cambiar aún quién lo escribe: nada de
   comportamiento cambia todavía y los tres consumidores quedan alineados.
2. Conectar la liberación en cancelar comanda —sólo ahí— y cablear el puerto en el servicio que
   atiende ese endpoint, no sólo en el de cocina.
3. Correr la migración de datos sobre las huérfanas existentes.
4. Ajustar las etiquetas del tablero, la vista del domiciliario y la condición del atajo al chat.
5. Rollback: revertir el código deja las filas ya canceladas en un estado que los consumidores
   viejos no conocen y volverían a contar como sin resolver — es decir, se vuelve al bloqueo
   original, nunca a un cobro o un cierre incorrecto.

## Open Questions

- ¿La cancelación de la comanda debería avisar al cliente por WhatsApp de que su domicilio no va?
  Hoy `cancel_order` ya manda `CUSTOMER_STATE_CANCELLED`, así que probablemente ya está cubierto —
  conviene confirmarlo antes de añadir nada.
