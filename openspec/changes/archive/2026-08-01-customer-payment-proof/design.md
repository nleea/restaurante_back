## Context

El sistema ya sabe cobrar un prepago: **verificar** es una sola acción humana que registra el
remanente (`total − pagado`) y manda el pedido a cocina, es idempotente y se niega entera si algo
falla (`delivery-settlement`). Lo que no existe es el otro lado del gesto — que el cliente pueda
decir "ya pagué" y enseñar el comprobante.

Tres hechos del código que mandan sobre este diseño:

- **`payments_total` es la fuente de "pagado"**, y de ella cuelgan la verificación de cocina
  (`is_payment_verified`), el cierre del pedido, la caja y el arqueo. Cualquier fila que se
  añada a `order_payments` es dinero a todos los efectos.
- **El paso de pago del checkout es decorado**: `needsProof` pinta un adjunto, `CreateOrderPayload`
  no lo lleva y nada se guarda. El cliente cree que lo mandó.
- **El prefirmado de `media` exige `menu.manage`**, así que hoy no hay ningún camino por el que un
  cliente pueda subir un archivo.

Y uno de producto: el cliente que llega aquí ya está en una pantalla que **no cobra** (por diseño,
`self-service-order-edit`). Esto no lo convierte en una caja: lo convierte en un buzón.

## Goals / Non-Goals

**Goals:**
- Que el cliente pueda mandar su comprobante en los dos momentos en que lo necesita: al pedir y
  cuando el total sube después.
- Que el personal se entere de que hay algo que verificar sin salir de donde ya verifica.
- Que ninguna declaración del cliente mueva un peso ni abra la cocina.
- Que el cliente sepa si se lo aceptaron.

**Non-Goals:**
- Pasarela de pago. Nadie cobra en línea aquí; esto entrega un papel, no dinero.
- Una bandeja de comprobantes por sucursal. Se ve sobre el pedido, que es donde está la decisión.
- Conciliación automática contra el banco. La mira una persona, como hoy.
- Que el comprobante adelante la cocina. Sigue haciéndolo la verificación, y sólo ella.

## Decisions

### 1. Una declaración NO es un pago, y por eso no vive en `order_payments`

Tabla propia (`order_payment_claims`): pedido, monto declarado, método, comprobante, estado
(`pending` / `accepted` / `rejected`), quién y cuándo la resolvió.

La alternativa —una fila en `order_payments` con `verified = false`— se descarta por una razón
concreta, no por gusto: `payments_total` la sumaría, `is_payment_verified` daría `true`, y **el
pedido entraría a cocina porque el cliente dijo que pagó**. Arreglarlo obligaría a auditar todas
las consultas de dinero del sistema —caja, arqueo, cierre, devoluciones— para excluir un estado
nuevo, y la primera que se olvidara sería un descuadre. Una tabla aparte no puede equivocarse:
lo que no está en `order_payments` no es dinero en ninguna pantalla.

```
  cliente declara  →  order_payment_claims (pending)   ← nadie cobra, nada se mueve
                            ↓ una persona mira
  verify_payment   →  order_payments (el remanente)    ← aquí, y sólo aquí, hay dinero
                   →  cocina
```

### 2. El archivo sube POR la API, no con una URL prefirmada

Contra la costumbre del proyecto (`media` prefirma contra R2), y a sabiendas.

Una URL prefirmada no puede acotar el tamaño de lo que se sube: la firma autoriza un PUT y el
cliente decide cuántos bytes mete. En una superficie **pública** —cualquiera con un enlace vivo—
eso es un bucket abierto con temporizador. Pasando los bytes por la API, FastAPI rechaza por tipo
y por tamaño antes de que nada se escriba, que es la única forma de que el límite sea real.

El archivo acaba igualmente **en R2**: la API valida los bytes y los sube ella misma, reusando la
firma que ya existe (`R2Storage.presign_put`) contra sí misma. No hace falta código de firma nuevo
ni boto3, y las credenciales siguen sin salir del servidor.

El coste es ancho de banda y memoria del backend por cada foto. Es asumible: un comprobante es una
captura de pantalla, y el tope se fija bajo (≈5 MB). Si algún día esto crece, la salida es
prefirmar con política (POST policy, que sí acota tamaño), no volver al PUT prefirmado.

### 3. El comprobante se ata al token del pedido, no a una sesión

Quien sube es quien tiene el enlace, y sólo puede subir **a ese pedido**. No hay parámetro de
pedido en la petición: sale del token, igual que en «mi pedido». Un token vencido no sube nada,
así que la superficie muere con el enlace.

Tope de declaraciones pendientes por pedido (3). No es para el disco: es para que la pantalla del
personal no se llene de intentos y siga siendo una decisión de un vistazo.

### 4. Verificar resuelve la declaración; no la necesita

`verify_payment` no cambia de forma: sigue registrando el remanente y enrutando. Se le añade que
marque como `accepted` las declaraciones pendientes de ese pedido y deje anotado cuál se miró.

*El orden importa:* una persona puede verificar sin que haya ninguna declaración (miró el Nequi en
su teléfono), y eso tiene que seguir funcionando igual. La declaración es una **ayuda para
decidir**, no un requisito para cobrar. Atarlas al revés —"no se puede verificar sin comprobante"—
crearía pedidos incobrables por un archivo que nunca llegó.

Rechazar es su propio gesto, con motivo, y no cobra nada: el comprobante era de otro pedido, la
cifra no coincide, la imagen no se lee. Un rechazo deja al cliente poder mandar otro.

### 5. El total puede subir después de pagar, y la cuenta la lleva el remanente

Es el caso que originó todo esto: pedido de 40.000 verificado, el cliente añade 2.500. Como
`verify_payment` cobra `total − pagado`, verificar otra vez cobra exactamente 2.500 sin tocar lo
anterior. La declaración nueva dice "pagué 2.500" y la vieja sigue aceptada.

Se enseña siempre **lo que falta**, nunca "el total": el cliente que ya pagó 40.000 y ve "paga
42.500" cree que le están cobrando dos veces.

### 6. WhatsApp sigue siendo una salida válida, y se dice

La pantalla de pago ofrece las dos: adjuntar aquí o **mandarlo por el WhatsApp del negocio**. No
es redundancia — es la ruta que la gente ya usa, la que funciona cuando la subida falla o cuando
el comprobante está en otro teléfono, y la única que deja al cliente hablando con una persona si
algo no cuadra.

Un comprobante que llega por el chat NO crea declaración: entra al inbox como cualquier foto y lo
mira quien atiende. Intentar adivinar de qué pedido es una imagen suelta sería inventar, y una
declaración mal atada es peor que ninguna.

### 7. Se cierra el bucle: al aceptar, el cliente se entera

Reusa el canal que ya avisa "recibimos tu pedido". Sin esto, el cliente manda el comprobante a un
buzón mudo y no sabe si puede contar con su pedido. Un aviso al aceptar, y otro al rechazar con
el motivo.

Y el que acepta es una persona **mirando que la plata llegó de verdad**: el sistema no comprueba
nada contra el banco. Por eso el gesto vive en la comanda, junto al botón que manda a cocina —
son el mismo momento (*"llegó, que lo hagan"*) y separarlos crea el pedido pagado que nadie
cocina.

## Risks / Trade-offs

- **Subida pública = superficie de abuso.** → Token vivo, tipo de imagen, tope de tamaño, tope de
  pendientes por pedido, y el objeto namespaceado por tenant y pedido. No se elimina: se acota y
  se puede apagar por tenant.
- **El personal ahora tiene una cosa más que mirar.** → Aparece donde ya está la decisión (el
  pedido), no en una bandeja nueva que nadie abre.
- **Un comprobante falso llega igual que uno bueno.** Es el mismo riesgo que hoy con la foto por
  WhatsApp, con la diferencia de que ahora queda guardado junto al pedido y con hora. → Lo mira
  una persona, como siempre; el cambio mejora el rastro, no la detección.
- **Fotos que nadie borra.** → Ciclo de vida en el bucket y borrado con el pedido; la política
  concreta se decide al implementar el almacenamiento.
- **El checkout que hoy "adjunta" y no guarda va a empezar a guardar.** → Es un arreglo, pero
  cambia lo que el personal recibe el primer día: hay que avisar antes de desplegarlo.
