## Why

El domicilio se muestra hoy como una tarifa fija en la carta pública, pero no forma parte del
total autoritativo del pedido. Además, esa tarifa no refleja los kilómetros que realmente debe
recorrer el repartidor. El negocio necesita aceptar el pedido primero, cotizar después su ruta por
vía y cobrar el total definitivo mediante WhatsApp antes de enviarlo a cocina.

## What Changes

- Añadir una cotización de domicilio por sucursal basada en distancia geodésica y un colchón fijo
  de 0,7 km, sin depender de un proveedor de rutas por carretera.
- Permitir configurar tarifas escalonadas por kilómetros y un límite máximo de cobertura por
  sucursal.
- Crear una fase de pedido pendiente de cotización: la toma del pedido no exige conocer ni elegir
  el medio de pago.
- Cuando la dirección tenga coordenadas, calcular y congelar el cargo de domicilio, su distancia
  y el total definitivo en la orden. Una corrección de dirección invalida la cotización previa.
- Enviar al contacto de WhatsApp del cliente una solicitud de pago con el total cotizado y un
  enlace seguro para elegir el medio de pago y declarar/enviar su comprobante.
- Mantener la verificación humana existente: una solicitud o comprobante nunca registra dinero ni
  manda comida a cocina por sí sola.
- **BREAKING**: el checkout público deja de presentar/cobrar una tarifa fija y deja de requerir el
  medio de pago al crear un domicilio; el total inicial deja de ser el total a pagar.

## Capabilities

### New Capabilities

- `delivery-quote-payment`: cotización asíncrona de distancia por vía, tarifas por kilómetros,
  congelamiento del cargo y solicitud de pago al cliente.

### Modified Capabilities

- `delivery-management`: una dirección geocodificada dispara o habilita la cotización; editarla
  invalida la cotización y la cobertura se decide por ruta calculada.
- `order-management`: el total incorpora un cargo de domicilio cotizado y la orden conserva su
  estado pendiente de cotización/pago de manera auditable.
- `delivery-settlement`: los domicilios prepagados sólo pueden entrar a cocina tras cotización y
  verificación del pago del total final.
- `storefront-public-api`: el intake público de domicilios crea un pedido pendiente de cotización
  sin exigir un medio de pago.
- `whatsapp-messaging`: el sistema puede emitir una solicitud de pago de domicilio al contacto
  vinculado, sin que una falla de mensajería altere la cotización ni el pedido.
- `frontend-storefront`: la carta pública explica que el valor de domicilio se confirmará por
  WhatsApp y elimina la tarifa/método de pago provisional.
- `frontend-delivery`: la sucursal administra sus bandas de precio por kilómetros y puede ver el
  estado de cotización de sus domicilios.

## Impact

- Backend: modelos/migraciones de órdenes y delivery, worker de geocodificación/cotización,
  estimador de distancia detrás de un puerto intercambiable, APIs de tarifas y solicitud de pago,
  y emisión de WhatsApp.
- Frontend: checkout público, tablero de domicilios y configuración de delivery.
- Integraciones: no se requiere proveedor de ruteo; WhatsApp sólo se usa cuando el pedido está
  vinculado a un contacto alcanzable.
- Pagos: se reutilizan los comprobantes y la verificación humana existentes; una pasarela de pago
  automática queda fuera de alcance.
