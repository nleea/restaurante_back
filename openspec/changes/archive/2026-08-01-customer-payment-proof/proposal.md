## Why

Un cliente que elige transferencia **no tiene por dónde mandar el comprobante**. El paso de pago
de la carta enseña "adjunta tu comprobante", pero el archivo no viaja con el pedido ni se guarda
en ninguna parte: es decorado. Y desde que existe «mi pedido», el hueco se ve más — el cliente
sube su total añadiendo algo y se queda mirando un "por pagar" sin ningún sitio donde pagarlo.

Del otro lado, el personal ya tiene el gesto que falta: **verificar el pago** registra el
remanente y manda el pedido a cocina en una sola acción. Lo que no tiene es la señal de que hay
algo que verificar; hoy la recibe por WhatsApp, a mano, o no la recibe.

## What Changes

- El cliente puede **declarar que pagó** y **adjuntar el comprobante**, tanto al hacer el pedido
  como después desde «mi pedido» cuando el total sube.
- Una declaración es una **afirmación, nunca un pago**: no toca el saldo, no abre la cocina y no
  cambia el estado del pedido. Sólo la verificación de una persona registra dinero — lo que ya
  hace `verify_payment` hoy, sin cambiarlo.
- El personal ve **"comprobante por verificar"** sobre el pedido, con la imagen y lo que el
  cliente dice haber pagado, y verifica desde donde ya verifica.
- El comprobante sube **por la API y acotado al token del pedido**: sin login, con tope de tipo
  y de tamaño comprobados antes de guardar nada, y la puerta muere cuando muere el enlace.
- El paso de pago del checkout deja de mentir: el `needsProof` que hoy no hace nada pasa a
  adjuntar de verdad.

**No cambia:** cobrar sigue siendo del personal. No se integra ninguna pasarela, no se confirma
ningún pago solo y un comprobante subido no adelanta la cocina ni un segundo.

## Capabilities

### New Capabilities
- `customer-payment-proof`: el cliente declara un pago y adjunta su comprobante; la declaración
  queda pendiente de verificación humana y no mueve dinero por sí sola.

### Modified Capabilities
- `storefront-public-api`: superficie pública nueva — subir el comprobante y declarar el pago,
  ambas acotadas por el token del pedido; el intake del pedido acepta el comprobante del
  checkout.
- `delivery-settlement`: la verificación —que ya registra el remanente— pasa a ser también el
  punto donde se resuelve una declaración del cliente, y deja constancia de qué comprobante se
  miró.
- `frontend-storefront`: el paso de pago adjunta de verdad el comprobante que hoy sólo enseña, y
  «mi pedido» ofrece pagar la diferencia con ese mismo paso en vez de mandar a escribir por
  WhatsApp.

## Impact

- **Backend**: `orders` (tabla propia de declaraciones + la consulta que el panel necesita),
  `storefront` (dos endpoints públicos por token), almacenamiento del archivo, una migración.
  `media` NO cambia: el prefirmado sigue siendo sólo de administración (ver design, decisión 2).
- **Frontend**: `PaymentStep.vue` (adjuntar de verdad), `MyOrderView.vue` (pagar la diferencia),
  y la pantalla del personal donde hoy se verifica (`OrderDetailView` / comanda).
- **Riesgo principal**: una subida pública es superficie de abuso. Se acota con el token, el
  tipo, el tamaño y un límite por pedido.
- **Depende de**: `self-service-order-edit` (el token del pedido y la vista «mi pedido»).
