## Why

El proceso real de un pedido por transferencia, contado por quien lo vive:

> *"Yo pido, hago todo, y si es transferencia no me debe bloquear: sólo me debe decir que mande el
> comprobante a este WhatsApp o lo adjunte aquí. **Me salgo, voy a donde voy a pagar**, y el banco
> me ofrece compartirlo por WhatsApp. Ahí el pedido ya debe estar, pero no en cocina, porque no se
> ha visto el pago. Entonces el que maneja el WhatsApp debe saber de qué pago fue y qué se pidió.
> Y luego el empleado lo revisa y le da confirmar en la comanda."*

Contra el código, tres de esos pasos ya funcionan y **cuatro están roto o mudos**:

```
✅ el checkout no bloquea         (:disabled="!selected" — sólo exige elegir método)
✅ el pedido nace activo y NO en cocina  (needsPaymentVerification)
✅ confirmar el pago desde la comanda    (PaymentSheet, permiso orders.pay)

❌ la pantalla de confirmación NO DICE NADA del comprobante si eligió WhatsApp
   (sólo habla si adjuntó: `v-else-if="cart.paymentProof"`)
❌ y el estado dice «En preparación» — que es MENTIRA: la cocina no lo ha visto
❌ el enlace es `wa.me/<sede>` SIN texto: llega una foto sin contexto y el agente
   no sabe de qué pedido es ni de cuánto
❌ nada le dice al cliente por WhatsApp que se está esperando su pago
```

El más caro de los cuatro es el `«En preparación»`. Es la fábrica de *"¿ya está listo?"* y de
decepciones en la puerta: el cliente cree que su comida se está haciendo cuando en realidad está
detenida esperando que alguien vea un comprobante que quizá ni ha mandado.

Y el más barato —una línea— es el que resuelve la frase central del problema (*"debe saber de qué
pago fue y qué se pidió"*): meter el número de pedido y el total en el texto prellenado del enlace.

## What Changes

- **La pantalla de confirmación deja de mentir.** Un pedido prepago sin verificar no dice
  «En preparación»: dice **«Esperando tu pago»**, que el pedido está guardado, y que entra a cocina
  en cuanto se vea el comprobante. Lo mismo en «mi pedido»: el mismo hecho contado igual en los dos
  sitios.
- **El enlace de WhatsApp lleva el pedido escrito.** `wa.me/<sede>?text=…` con el código y el
  total, así que **el primer mensaje del cliente ES el contexto** que el agente necesita. Y de paso
  respeta la invariante del canal: el cliente escribe primero, así que a partir de ahí sí se le
  puede contestar.
- **Un aviso nuevo, `awaiting_proof`, que REEMPLAZA al de "recibimos tu pedido"** cuando el pedido
  nace prepago y sin pagar. Reemplaza y no se suma: dos mensajes por el mismo hecho es
  exactamente el volumen de salida que hace que WhatsApp mire un número. Texto editable por el
  dueño, como los otros seis.
- **Una tercera variante del saludo**, para el cliente que llega en frío y su primer mensaje es el
  comprobante. Hoy recibiría *"¡Hola! Bienvenido, mira nuestra carta 👋"* encima de su recibo. La
  variante se elige **por estado del pedido, no por el texto** —"este contacto tiene un pedido
  esperando pago"— así que **no rompe la regla #1 del módulo**: el saludo sigue sin leer lo que el
  cliente escribió.
- **El comprobante puede nacer de un mensaje del chat.** En la bandeja, sobre una imagen o un PDF:
  *"usar como comprobante de…"* → crea el claim con esa imagen y el importe precargado con el saldo.
  **Nunca automático**: una foto no es una declaración de pago, y un claim creado solo por llegar una
  imagen acaba siendo el comprobante que era la foto de un perro.
- **La comanda enlaza al chat.** Con las imágenes ya dentro (`whatsapp-inbound-media`), el enlace va
  a la **bandeja interna** y no a WhatsApp: no se sale del producto y no hace falta que ese
  dispositivo tenga la sesión de la sede.
- **Queda rastro.** El `proof_url` se rellena de verdad, así que una discusión tres meses después
  tiene algo que mirar. Es la diferencia con mandar al empleado a mirar el teléfono.

## Capabilities

### Modified Capabilities

- `customer-payment-proof`: un claim puede nacer de un mensaje del chat, creado por una persona que
  mira la imagen — no sólo de la subida del cliente por el enlace del pedido. Las cinco reglas que
  ya tiene (un claim no es un pago; lo resuelve una persona en los dos sentidos; el cliente se
  entera del resultado; hay un techo por pedido) **siguen mandando sin excepción**.
- `whatsapp-autoreply`: gana el aviso `awaiting_proof` —séptimo estado de cara al cliente, mutuamente
  excluyente con "recibimos tu pedido"— y la tercera variante del saludo, elegida por el estado del
  pedido y no por el texto del cliente.
- `frontend-whatsapp-inbox`: sobre una imagen del hilo, la acción de usarla como comprobante de un
  pedido del contacto.
- `frontend-storefront`: el estado honesto de un prepago sin verificar, y el enlace de WhatsApp con
  el pedido prellenado.

## Impact

- **Depende de `whatsapp-inbound-media`.** Sin las imágenes dentro, la acción de "usar como
  comprobante" no tiene de qué agarrar y el enlace de la comanda tendría que salir a WhatsApp.
  El resto del change (el aviso, el saludo, el enlace prellenado, el estado honesto) **no** depende
  de él y podría aplicarse antes.
- **Depende de que `customer-payment-proof` esté archivada**, para hacer delta sobre una capability
  que exista en `openspec/specs/`. Su única tarea pendiente era la prueba manual, ya hecha.
- **Backend**: séptimo estado en la lista cerrada `CUSTOMER_STATES` (toca la validación del mapeo y
  la clave de emisión); tercera plantilla de saludo en los ajustes por tenant; endpoint para crear
  un claim desde un mensaje del chat (permiso `orders.pay`, no `messaging.*` — es dinero).
- **Migración 0033**: la tercera plantilla de saludo en los ajustes. El estado nuevo no necesita
  esquema: el mapeo es JSON.
- **Frontend**: copy honesto en dos vistas públicas, el `?text=` del enlace, y la acción en la
  bandeja.
- **Permisos**: una sola persona hace todo el recorrido (ve el chat y confirma), así que necesita
  `messaging.read` **y** `orders.pay`. No se inventa mecanismo de traspaso entre dos personas
  porque en el piloto no existen dos personas.
- **Volumen de salida**: no sube. `awaiting_proof` sustituye a un aviso que ya salía, y el techo de
  cuatro mensajes por pedido se mantiene (`awaiting_proof` → pago confirmado → va en camino →
  entregado).
- **Lo que NO cambia**: el pedido sigue sin entrar a cocina hasta que una persona verifica, y eso lo
  decide `payments_total`, no este change. Aquí sólo se hace visible **por qué** está detenido.
