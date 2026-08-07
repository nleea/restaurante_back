## Context

Este change no inventa un flujo: describe el que ya ocurre y tapa los cuatro sitios donde el sistema
se calla o miente. El recorrido, con lo que existe marcado:

```
CLIENTE                        SISTEMA                      EMPLEADO (una sola persona)
  ├─ pide · transferencia
  │              ✅ pedido activo, NO en cocina
  │                 (needsPaymentVerification = método≠efectivo && pagado<total)
  │              ✱  «Esperando tu pago» en vez de «En preparación»
  │              ✱  awaiting_proof al WhatsApp del cliente, si hay hilo
  │              ✱  si no hay hilo: wa.me?text=«mi pedido A3F2 por $46.000»
  ├─ se sale a pagar
  ├─ el banco ofrece «compartir por WhatsApp»
  ├─ manda la captura
  │              ✅ la imagen se guarda y se ve en la bandeja  (whatsapp-inbound-media)
  │                                            ├─ la ve SIN salir del producto
  │                                            ├─ ✱ [usar como comprobante de A3F2]
  │                                            └─ ✅ [confirmar] en la comanda
  │              ✅ registra el pago → cocina desbloqueada
  │  ← ✅ «confirmamos tu pago» con el detalle de lo pedido
```

Lo que ya está construido y este diseño se apoya en ello:

- **La verificación no depende de claims.** `needsPaymentVerification` es método≠efectivo y sin
  pagar; el bloque "Pago por confirmar" de la comanda **ya aparece** para estos pedidos y ya
  reemplaza al botón de cocina. Lo que falta ahí no es la lógica: es que diga dónde está el
  comprobante.
- **La miniatura del claim ya degrada bien**: es `v-if="claim.proof_url"`, así que un claim sin
  imagen no pinta nada roto.
- **El aviso "recibimos tu pedido" ya lleva el detalle y el total** — el único de los seis que lo
  lleva, y por una razón escrita: es el mensaje que el cliente relee para comprobar que le
  entendimos.
- **`has_live_order`** (de `whatsapp-keyword-faqs`) contesta "¿este contacto tiene un pedido vivo?",
  que es justo la pregunta del saludo nuevo y del selector de pedido al usar una imagen como
  comprobante.
- **El claim ya sabe existir sin archivo**: `proof_url` es nullable y su comentario dice *"Nulo si
  llegó por otra vía (el chat, una llamada)"*. Este change es, en parte, cumplir ese comentario.
- **Resolver un claim ya registra el pago y avisa al cliente** con el detalle. Nada de eso se
  reescribe.

## Goals / Non-Goals

**Goals**

- Que el cliente sepa, en el momento en que se va a pagar, **qué falta y dónde mandarlo**.
- Que el cliente no crea que su comida se está haciendo cuando está detenida.
- Que quien atiende sepa **de qué pedido es** la foto que acaba de llegar, sin preguntar.
- Que el comprobante quede **dentro** del pedido, no en la memoria de quien lo miró.
- Que todo el recorrido lo pueda hacer una persona sin salir del producto.

**Non-Goals**

- **Bloquear el checkout.** Es explícitamente lo contrario de lo que se pide, y ya no bloquea.
- **Verificar automáticamente.** Nadie compara el importe de la captura con el total. Lo que hace un
  humano al mirar un comprobante es decidir si la plata llegó, y eso no lo sabe el sistema.
- **Convertir una imagen en un claim sola.** Ver decisión 5.
- Cobrar deudas de fiado con un comprobante. Los claims cuelgan de un pedido (`order_id` NOT NULL);
  el fiado es otra conversación.
- Un mecanismo de traspaso entre "el del WhatsApp" y "el de la comanda": es la misma persona.

## Decisiones

### 1. `awaiting_proof` reemplaza a "recibimos tu pedido"; no se suma

Séptimo estado de cara al cliente. Sale **en vez** del acuse normal cuando el pedido nace prepago
(`payment_method != cash`) y sin pagar.

```
prepago sin pagar:   awaiting_proof → (pago confirmado) → va en camino → entregado   = 4
efectivo:            recibimos tu pedido → va en camino → entregado                  = 3
```

Sumarlos daría cinco y el techo son cuatro — y ese techo no es pereza: es *"la defensa principal
contra que marquen el número"*, escrito en el propósito de la capability.

Texto de fábrica editable, con los marcadores de pedido que ya existen:

> *Recibimos tu pedido `{order_number}` · `{order_total}`. Lo tenemos guardado y entra a cocina en
> cuanto veamos tu comprobante — mándalo por aquí. `{order_items}`*

**Rechazado: añadir un párrafo por código al aviso de siempre.** Es exactamente la queja que
originó el trabajo de esta semana: una línea que el código pega al final y que el dueño no puede
quitar editando el texto. Dos situaciones distintas, dos textos que el dueño ve y edita.

**Rechazado: un marcador tipo `{payment_pending}`** que se resuelva sólo cuando falta el pago. Es
elegante y es peor de explicar: el dueño tendría un texto que dice dos cosas distintas según un
estado invisible. Con dos plantillas, lee las dos y sabe cuál sale cuándo.

### 2. La tercera variante del saludo se elige por ESTADO, no por texto

El caso: el cliente llegó por la web, nunca escribió al número, y su primer mensaje es la foto del
comprobante. El saludo es incondicional y no lee el texto —regla #1 del módulo, deliberada— así que
hoy le contesta *"¡Hola! Bienvenido a X 👋 Mira nuestra carta y haz tu pedido aquí"*. Encima de su
recibo.

```
saludo, al llegar el primer mensaje
   ├─ ¿el contacto tiene un pedido vivo SIN PAGAR?   ← estado, no palabras
   │     └─ sí → variante «esperando tu pago»:
   │             «¡Hola! Vimos tu pedido A3F2 por $46.000. Si ya pagaste, mándanos
   │              el comprobante por aquí y lo confirmamos.»
   ├─ ¿abierto?  → variante de abierto      (como hoy)
   └─ cerrado    → variante de cerrado      (como hoy)
```

**No rompe la regla #1**, y el matiz es todo: la regla prohíbe **detectar intención en el texto**
("una lista de palabras clave es una fábrica de bugs"). Esto no mira el texto — mira si hay un
pedido esperando pago, que es un hecho de la base. El saludo sigue siendo incondicional respecto a
lo que el cliente escribió: da igual si mandó una foto, "hola" o un sticker.

Efecto secundario que vale por sí solo: **pone el contexto del pedido en el hilo**, así que el
agente que abra la conversación lee el número y el total encima de la foto — el requisito de "debe
saber de qué pago fue" resuelto incluso si el cliente no usó el enlace prellenado.

### 3. El enlace prellenado es lo que hace posible el caso "en frío"

La invariante del canal es que **nunca se inicia una conversación**. Para el cliente que pidió por la
web y nunca escribió, eso significa que no podemos avisarle de nada. El sustituto:

```
wa.me/<sede>?text=Hola, mi pedido A3F2 por $46.000. Aquí va mi comprobante.
```

Él pulsa enviar, **él inicia**, la invariante se cumple sola, y su primer mensaje ya trae lo que el
agente necesita. Una línea de código para el problema que se planteó como central.

Detalle que no es cosmético: el texto tiene que llevar el **código del pedido** y el **total**. Sin
el total, el agente tiene que ir a buscar cuánto era para saber si el comprobante cuadra.

### 4. Decir la verdad del estado, en los dos sitios

`«En preparación»` para un pedido que la cocina no ha visto es una mentira con consecuencias: genera
el *"¿ya está listo?"* y la decepción en la puerta. El estado se deriva, no se inventa:

```
prepago && pagado < total   →  «Esperando tu pago»
                               «Tu pedido está guardado. Entra a cocina en cuanto
                                veamos tu comprobante.»
resto                        →  lo de hoy
```

Y en **los dos sitios donde el cliente lo lee**: la confirmación del checkout y «mi pedido». El mismo
hecho contado igual, con una función de presentación compartida — si se escribe dos veces, en tres
meses dicen cosas distintas.

### 5. Una imagen no se convierte en comprobante sola

La acción vive en la bandeja y la ejecuta una persona: *"usar como comprobante de…"*, con un selector
de los pedidos vivos sin pagar de ese contacto (normalmente uno) y el **importe precargado con el
saldo**, editable — quien la pulsa está mirando el recibo, así que corregir el número es gratis para
él y adivinarlo es imposible para el sistema.

**Rechazado: crear el claim automáticamente** cuando llega una imagen de alguien con un pedido sin
pagar. Los clientes mandan fotos de la calle, memes, su cédula, el plato de ayer. Un claim
automático es, tarde o temprano, un "comprobante" que es la foto de un perro — y el mostrador
aprende a ignorar el aviso, que es la peor de las dos consecuencias.

**Rechazado también: crear el claim al confirmar el pedido** (un claim "vacío" en el checkout, para
que la comanda diga "espera comprobante"). Un claim significa *el cliente declara que pagó*, y en el
checkout **todavía no ha pagado**: sería una declaración falsa por diseño. La comanda ya sabe que
falta verificar sin necesidad del claim; lo que le falta es el texto y el enlace.

El permiso es **`orders.pay`**, no `messaging.attend`: crear un claim es un paso del camino del
dinero. Que la misma persona tenga los dos permisos es una realidad del piloto, no una excusa para
mezclarlos.

### 6. El enlace de la comanda va a la bandeja, no a WhatsApp

Con `whatsapp-inbound-media` aplicado, la imagen está en la bandeja. Entonces el enlace correcto es
el interno (`/whatsapp` con la conversación seleccionada):

| | bandeja interna | WhatsApp real (`wa.me`) |
|---|---|---|
| ¿se ve el comprobante? | **sí**, con el change de multimedia | sí |
| ¿hace falta la sesión de la sede en ese dispositivo? | **no** | sí |
| ¿se sale del producto? | **no** | sí |

Sin el change de multimedia, la bandeja enseñaría el marcador y el enlace interno sería una trampa
—llevar al empleado a un sitio donde no puede ver lo que fue a ver—. De ahí la dependencia.

## Riesgos

- **El cliente nunca manda el comprobante.** El pedido se queda esperando. Es correcto (no se cocina
  sin pago) pero alguien tiene que barrer esos pedidos algún día. Fuera de alcance; candidato claro
  a una alerta del módulo de alertas.
- **La misma foto usada dos veces** para dos pedidos. El techo de claims por pedido ya existe; que la
  misma imagen sirva dos veces es una decisión humana y la resuelve quien mira.
- **El estado honesto puede leerse como "no pagué"** por un cliente que sí pagó y ya mandó el
  comprobante. El texto tiene que distinguir *"esperando tu pago"* de *"revisando tu comprobante"*
  si hay un claim pendiente — es una tercera frase, y es la que evita la pregunta.
- **`awaiting_proof` en un pedido de mostrador** con método tarjeta: nace prepago y sin pagar, así
  que le tocaría el aviso. Pero un pedido de mostrador no suele tener contacto de WhatsApp, y sin
  contacto no sale nada. Conviene comprobarlo, no suponerlo.

## Preguntas abiertas (no bloqueantes)

- ¿Se distingue en la comanda "todavía no ha llegado nada" de "llegó una imagen a las 19:42"? Con
  `media_type` guardado (viene del change de multimedia) es un dato disponible, y es la pregunta que
  el empleado tiene de verdad. Se deja fuera de este change para no atarlo al otro más de lo
  necesario.
- ¿El aviso `awaiting_proof` debería repetirse si pasan N horas sin comprobante? Sería el primer
  automático que sale **sin** que el cliente escriba antes: hay que mirarlo contra la invariante del
  canal antes de proponerlo.
- ¿Qué pasa con un pedido prepago cuyo cliente paga en efectivo en la puerta? Hoy se resuelve
  registrando el pago a mano; el aviso ya salió diciendo que se esperaba un comprobante.
