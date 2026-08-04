## Context

La carta pública crea pedidos a domicilio con dirección o GPS. La geocodificación de una dirección
es asíncrona y los anillos de delivery sólo son una vista operativa de distancia aérea. A la vez,
el frontend muestra una tarifa fija que no se persiste ni integra al total autoritativo de la
orden. Los comprobantes ya son declaraciones verificadas por una persona y los pedidos pueden
estar vinculados a un contacto de WhatsApp.

Esta propuesta convierte ese intervalo entre tomar el pedido y cobrarlo en un flujo explícito:
primero se cotiza la distancia geodésica ajustada, luego se solicita el pago y finalmente se verifica antes
de que cocina reciba un pedido prepagado.

## Goals / Non-Goals

**Goals:**

- Cobrar domicilio por kilómetros geodésicos más un colchón fijo de 0,7 km, con bandas de precio
  configurables por sucursal.
- No bloquear la toma del pedido por geocodificación o ruteo.
- Guardar una cotización inmutable y auditable antes de pedir pago.
- Separar la elección del método de pago del intake del pedido y entregar un enlace de pago seguro
  por WhatsApp cuando exista un contacto alcanzable.
- Reutilizar los comprobantes y la verificación humana; los totales del backend son la única
  fuente de verdad.

**Non-Goals:**

- Cobrar automáticamente con una pasarela o verificar transferencias de forma automática.
- Optimizar recorridos con múltiples paradas, estimar ETA, o reemplazar los anillos del mapa.
- Garantizar que todo pedido tenga WhatsApp: los no vinculados quedan para revisión/envío manual.
- Recalcular y cobrar retroactivamente pedidos que ya existen.

## Decisions

### La distancia de precio es geodésica ajustada y los anillos continúan operativos

El worker toma las coordenadas finales de la entrega y el pin de la sucursal, calcula su distancia
geodésica con Haversine y suma un colchón fijo de 0,7 km antes de seleccionar la banda de tarifa. Los
anillos siguen sirviendo para cobertura visual, asignación y despacho, pero no deciden el precio.

Se elige este cálculo frente al ruteo por calles para no depender de un proveedor externo ni
bloquear la cotización. El colchón es una corrección comercial explícita, no una estimación de la
ruta real, y se guarda con la cotización para auditoría. El cálculo vive detrás del puerto
`DistanceEstimator`: la implementación inicial es `HaversineBufferedEstimator`; una futura
implementación de gateway de rutas podrá devolver kilómetros de conducción con el mismo contrato.
Cada cotización también guarda el método usado, para que un pedido histórico nunca se reinterprete
al cambiar de estimador.

### La tarifa se configura como bandas inclusivas superiores por sucursal

Una banda contiene `max_distance_km` y `fee`; se selecciona la primera cuyo máximo cubra la
distancia. La última banda define el máximo de cobertura. Las bandas son ordenadas, no se solapan
y no dejan huecos desde cero. Esto expresa la política comercial (“hasta 2 km vale X”) sin los
problemas de redondeo de una fórmula por kilómetro.

Se prefiere a una tarifa lineal por km porque el negocio pidió valores distintos por rangos y el
cliente recibe una cifra simple. Una futura fórmula puede añadirse como otro tipo de plan sin
cambiar la cotización congelada.

### La cotización vive en la entrega y su importe congelado en la orden

`OrderDelivery` conserva estado de cotización, distancia, banda aplicada, fecha y motivo de
rechazo/revisión. `Order` conserva `delivery_fee`, que participa en `total` junto a subtotal y
descuento. Al cotizar se escriben ambos dentro de una unidad transaccional; el total no se deriva
del plan vigente después del hecho.

Editar dirección o coordenadas invalida la cotización, elimina el cargo de domicilio y vuelve a
encolar el cálculo. Una entrega fuera de cobertura o no resoluble no se cobra ni llega a cocina.

### La solicitud de pago es una entidad con token propio

Al quedar cotizado un pedido se crea una `payment_request` de un solo uso para su versión de
cotización, con token aleatorio almacenado como hash, fecha de emisión y estado. El enlace permite
elegir método y crear un payment claim por el saldo vigente, pero no editar productos ni dirección.
Una nueva cotización invalida la solicitud anterior antes de emitir otra.

Se prefiere al token de edición del pedido: reduce la autoridad del enlace y evita que un enlace de
pago permita cambiar un total ya cotizado. La selección del método actualiza el intento de pago de
la orden, sin registrar dinero.

### El envío de WhatsApp es una consecuencia reintentable, no una transacción de dinero

Tras crear la solicitud, una emisión idempotente intenta enviarla solamente a un contacto de
WhatsApp alcanzable. La cotización queda válida aunque el envío falle; el tablero expone ese estado
para reintentar o contactar al cliente manualmente. Un idempotency key por solicitud evita dos
mensajes para la misma cotización.

### El token en claro sólo existe al crear la solicitud, y eso define dónde se emite

De la solicitud sólo se persiste `token_hash`; el token legible es transitorio. Dos consecuencias
que no son opcionales:

1. La emisión debe ocurrir dentro de la misma unidad que crea la solicitud —un worker posterior que
   lea la tabla no puede construir el enlace—, así que vive en la pasada de cotización.
2. "Reintentar" no es reenviar: es **re-emitir**. Un envío fallido se recupera creando una solicitud
   nueva para la misma cotización sin cambios, que invalida la anterior. Guardar el token en claro
   para poder reenviarlo convertiría la tabla en un almacén de credenciales de pago, que es
   exactamente lo que el hash evita.

Se acepta el costo: un enlace que el cliente perdió no se puede "volver a mandar" idéntico. A
cambio, una filtración de la base de datos no entrega ningún enlace de pago utilizable.

### La cocina exige cotización resuelta y pago verificado para delivery prepagado

El pedido público a domicilio comienza sin `payment_method`. Después de la cotización, el enlace
recoge la elección. Para métodos prepagados, el flujo de settlement existente verifica el pago del
total que ya incluye domicilio y libera cocina. Si el negocio habilita efectivo, también recibe la
cotización por WhatsApp pero puede avanzar bajo las reglas vigentes de cobro contraentrega.

## Risks / Trade-offs

- [El colchón fijo no refleja todos los desvíos reales] → se muestra y persiste por separado, y el
  negocio puede ajustar su valor o sus bandas sin reinterpretar cotizaciones ya emitidas.
- [La geocodificación aproxima mal la dirección] → se conserva el pin y fuente de coordenadas,
  se permite corrección manual y una corrección invalida la tarifa anterior.
- [Una tarifa cambia mientras existen cotizaciones] → sólo afecta cotizaciones futuras; cada orden
  conserva banda, distancia y valor aplicados.
- [WhatsApp no está vinculado o no permite un envío] → no se bloquea el pedido ni la cotización;
  se marca para acción operativa y no se afirma que el link fue enviado.
- [El cliente abre un enlace viejo] → token de solicitud único, vencible e invalidado por una nueva
  cotización; el servidor rechaza el método o comprobante asociado a un total obsoleto.

## Migration Plan

1. Añadir las tablas/campos como nulos y desplegar lectores compatibles con órdenes antiguas.
2. Crear planes de tarifa y el colchón de 0,7 km por sucursal antes de habilitar cotización
   automática para ella.
3. Activar intake diferido en la carta pública: ya no manda método de pago ni usa `$6.000` local.
4. Encolar cotizaciones sólo para pedidos nuevos; los pedidos previos conservan sus totales.
5. Habilitar envío de solicitudes y observar fallos/reintentos antes de exigir cotización para
   liberar cocina.
6. Rollback: desactivar el feature por sucursal; las cotizaciones ya emitidas y sus solicitudes se
   siguen leyendo y verificando, mientras los nuevos pedidos vuelven al flujo anterior configurado.

## Open Questions

- Si efectivo contraentrega estará habilitado desde el primer lanzamiento o todos los pedidos
  cotizados serán prepagados.
- Cuánto dura una solicitud de pago antes de vencerse y quién puede renovarla.
