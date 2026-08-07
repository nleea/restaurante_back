> Lee `design.md`. **Depende de `whatsapp-inbound-media`** para los grupos 5 y 6 (sin las imágenes
> dentro, "usar como comprobante" no tiene de qué agarrar). Los grupos 1–4 no dependen de él y se
> pueden aplicar antes: el aviso, el saludo, el enlace prellenado y el estado honesto.
>
> También depende de que `customer-payment-proof` esté **archivada**, para hacer delta sobre una
> capability que exista en `openspec/specs/`.
>
> Orden: 1 → 2 → 3 → 4 (ya hay producto) → 5 → 6 → 7 → 8.

## 1. Backend — el aviso `awaiting_proof`

- [x] 1.1 Séptimo estado en `CUSTOMER_STATES` (`shared/customer_channel/ports.py`) y en el mapeo de
      fábrica, **encendido** como el acuse que sustituye
- [x] 1.2 Texto de fábrica con `{order_number}`, `{order_total}` y `{order_items}`, diciendo que el
      pedido está guardado y entra a cocina cuando se vea el comprobante
- [x] 1.3 En la creación del pedido: si es prepago (`payment_method != cash`) y `payments_total == 0`,
      se emite `awaiting_proof` **en vez de** `order_received`. Mutuamente excluyentes
- [x] 1.4 Prueba de que un pedido prepago recibe UNO de los dos, nunca los dos — es el requisito, no
      un detalle: dos mensajes por el mismo hecho es el volumen que hace que marquen el número
- [x] 1.5 Prueba de que un pedido en efectivo sigue recibiendo exactamente lo de hoy
- [x] 1.6 Prueba del techo: un prepago con el mapeo de fábrica no manda más mensajes que uno en
      efectivo
- [x] 1.7 Comprobar el caso del pedido de mostrador con método tarjeta: nace prepago, pero sin
      contacto de WhatsApp no sale nada. **Comprobarlo, no suponerlo**

## 2. Backend — la tercera variante del saludo

- [x] 2.1 Columna `greeting_awaiting_payment_text` en los ajustes; vacía cae a la variante de
      abierto/cerrado, **nunca a silencio**
- [x] 2.2 Elegir la variante en `render_greeting`: si el contacto tiene un pedido prepago sin pagar
      (reusar la consulta de `has_live_order` + saldo), gana esta variante
- [x] 2.3 El texto de fábrica nombra el pedido y el total y pide el comprobante
- [x] 2.4 Prueba de que la elección **NO lee el texto del cliente**: la misma variante sale con una
      foto sin pie, con "hola" y con una palabra cualquiera. Es lo que mantiene intacta la regla #1
- [x] 2.5 Prueba de que sin pedido sin pagar sale la variante de siempre
- [x] 2.6 Migración **0033_greeting_awaiting_payment** (up/down/up en Postgres, sin deriva)
- [x] 2.7 La cuarta variante entra en el editor de `/whatsapp/autoreply` con su vista previa, igual
      que las otras dos

## 3. Frontend — el enlace con el pedido escrito

- [x] 3.1 `wa.me/<sede>?text=…` con el código del pedido y el total. **Los dos**: sin el total, el
      agente tiene que ir a buscar cuánto era
- [x] 3.2 Sin teléfono de sede, no hay botón (ya es así); con pedido sin confirmar aún, tampoco
- [x] 3.3 Prueba de que el texto lleva código y total, y de que va URL-encoded (los `$` y los saltos
      de línea rompen el enlace si no)

## 4. Frontend — el estado honesto

- [x] 4.1 Una función de presentación **compartida** que derive el estado de cara al cliente:
      prepago sin pagar → "Esperando tu pago"; con claim pendiente → "Revisando tu comprobante";
      resto → lo de hoy. Si se escribe dos veces, en tres meses dicen cosas distintas
- [x] 4.2 Usarla en la confirmación del checkout: hoy sólo habla si adjuntó algo
      (`v-else-if="cart.paymentProof"`), y calla justo cuando el cliente se va a pagar
- [x] 4.3 Usarla en «mi pedido»
- [x] 4.4 Que **nunca** diga «En preparación» un pedido que la cocina no ha visto
- [x] 4.5 Pruebas de los cuatro estados en las dos vistas

## 5. Backend — el claim que nace del chat

- [x] 5.1 Caso de uso: mensaje del chat + pedido → claim con `proof_url` = el archivo del mensaje,
      importe recibido de quien lo crea, estado `pending`
- [x] 5.2 Sólo pedidos **del mismo contacto** y sin saldar. Un id de otro cliente se rechaza — y hay
      prueba, porque es un salto de tenant/cliente disfrazado de comodidad
- [x] 5.3 Permiso **`orders.pay`**, no `messaging.attend`: crear un claim es un paso del camino del
      dinero
- [x] 5.4 El techo de claims por pedido que ya existe **sigue mandando** por esta vía
- [x] 5.5 Marcar el mensaje como ya usado, para que no se adjunte dos veces
- [x] 5.6 Prueba de que **llegar no crea nada**: una imagen de alguien con pedido sin pagar no
      produce ningún claim hasta que una persona lo dice
- [x] 5.7 Prueba de que el claim resultante es indistinguible de uno subido por el cliente: se
      resuelve, registra el pago y avisa al cliente por los caminos que ya existen

## 6. Frontend — la acción en la bandeja y el enlace de la comanda

- [x] 6.1 En un mensaje con imagen o PDF: "usar como comprobante de…", con los pedidos elegibles
      (número + saldo) y el importe precargado
- [x] 6.2 **Oculta**, no deshabilitada, sin `orders.pay`
- [x] 6.3 Sin pedidos elegibles: se dice por qué, no un botón muerto
- [x] 6.4 Un archivo ya usado lo dice, nombrando el pedido
- [x] 6.5 En la comanda, dentro del bloque "Pago por confirmar" que YA aparece: decir que el
      comprobante puede venir por WhatsApp y enlazar **a la bandeja interna** con esa conversación
      (no a `wa.me`: ver la tabla del diseño §6)
- [x] 6.6 La bandeja tiene que poder abrirse con una conversación seleccionada por URL (hoy `/whatsapp`
      no lleva parámetro)
- [x] 6.7 Pruebas de la acción y del enlace

## 7. Pruebas de extremo a extremo

- [x] 7.1 El recorrido completo: pedido por transferencia sin adjuntar → aviso `awaiting_proof` →
      imagen entrante → "usar como comprobante" → confirmar en la comanda → el pedido entra a cocina
      y el cliente recibe "confirmamos tu pago"
- [x] 7.2 El recorrido "en frío": pedido web sin contacto de WhatsApp → enlace prellenado → primer
      mensaje del cliente → saludo con la variante de pedido esperando pago
- [x] 7.3 `ruff`, `mypy`, suite completa; `type-check`, `lint`, `test:unit`

## 8. Documentación

- [x] 8.1 `docs/messaging/ROADMAP.md`: el séptimo estado y por qué reemplaza en vez de sumarse
- [x] 8.2 Dejar escrito —donde se elige la variante del saludo— que la elección es **por estado y no
      por texto**, y que eso es lo que la hace compatible con la regla #1 del módulo. Sin esa nota,
      alguien la va a leer como una excepción a la regla y la va a "arreglar"
