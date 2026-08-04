> Depende de `self-service-order-edit` (el token del pedido y la vista «mi pedido»). Lee
> `design.md` antes de empezar: la decisión 1 —una declaración NO vive en `order_payments`— es el
> cambio entero; el resto es fontanería alrededor.

## 1. Backend — la declaración

- [x] 1.1 Entidad y tabla `order_payment_claims`: pedido, monto declarado, método, comprobante,
      estado (`pending`/`accepted`/`rejected`), motivo del rechazo, quién y cuándo lo resolvió
- [x] 1.2 Migración **0030_order_payment_claims** con su `down` (up/down/up en Postgres, sin
      deriva; el FK de sucursal es `RESTRICT` como el resto y el índice va por pedido a secas)
- [x] 1.3 Crear una declaración, con el tope de pendientes por pedido; nada de esto toca
      `order_payments` ni recalcula el pedido
- [x] 1.4 Listar las declaraciones de un pedido, y una consulta de "tiene pendientes" que el
      panel pueda pedir sin traerse las imágenes
- [x] 1.5 Rechazar con motivo: no registra dinero y deja al cliente poder mandar otra
- [x] 1.6 Pruebas de que **una declaración no mueve nada**: `payments_total`, saldo, estado y
      `is_payment_verified` idénticos antes y después

## 2. Backend — el archivo

- [x] 2.1 Guardar el comprobante pasando los bytes POR la API: tipo permitido y tope de tamaño
      comprobados ANTES de escribir (ver design, decisión 2; el prefirmado de `media` no sirve
      aquí porque no acota el tamaño)
- [x] 2.2 Subida a **R2** desde el servidor reusando `R2Storage.presign_put` contra sí mismo (sin
      firma nueva ni boto3); clave por tenant y pedido, y devolver la URL pública que verá el panel
- [x] 2.3 Vida del archivo: las FILAS caen con el pedido (`ON DELETE CASCADE`); los OBJETOS se
      dejan a una regla de ciclo de vida sobre el prefijo `payment-proofs/` del bucket, y no a un
      borrador en código — un pedido casi nunca se borra (se cierra), así que ese borrador no se
      ejecutaría nunca y sería código muerto haciéndose pasar por una garantía
- [x] 2.4 Pruebas: un tipo no permitido y un archivo por encima del tope se rechazan sin escribir

## 3. Backend — la verificación resuelve

- [x] 3.0 Endpoints del PERSONAL: listar las declaraciones de un pedido y rechazar una con
      motivo (`orders.pay`); verificar ya existe

- [x] 3.1 `verify_payment` marca `accepted` las pendientes del pedido y anota quién las miró,
      **sin cambiar** lo que ya hace (remanente + enrutado, atómicos)
- [x] 3.2 Verificar SIN ninguna declaración sigue funcionando igual: es una ayuda, no un requisito
- [x] 3.3 Aviso al cliente al aceptar y al rechazar (con motivo), por el canal que ya existe;
      sin canal alcanzable, la resolución ocurre igual y no se manda nada
- [x] 3.4 Pruebas: el pedido que sube de total tras verificarse cobra SÓLO la diferencia al
      volver a verificarse, y la declaración vieja sigue aceptada

## 4. Backend — la superficie pública

- [x] 4.1 `POST /storefront/orders/{token}/payment-proof` (multipart): el pedido sale del token
      y el MÉTODO sale del pedido, no del formulario — dejar re-elegir aquí sólo crea un cobro
      que no cuadra con el comprobante
- [x] 4.2 La misma llamada declara y devuelve el pedido **con el mismo saldo**: devolver un "ok"
      a secas se leería como "ya está pagado"
- [x] 4.3 Vencido / desconocido / de otro tenant: misma respuesta, sin filtrar existencia
- [x] 4.4 El `GET` de «mi pedido» informa si hay una declaración esperando confirmación
- [x] 4.5 **Sin endpoint nuevo**: el checkout crea el pedido (que ya devuelve `editToken`) y
      sube el comprobante por esa misma puerta. Meter el archivo en el intake habría duplicado
      la validación y obligado a un multipart en el único endpoint que hoy es JSON limpio; la
      declaración acaba igual atada al pedido, que es lo que pedía el spec
- [x] 4.6 Pruebas: subir a un pedido ajeno es imposible; el saldo no se mueve al declarar

## 5. Frontend — el paso de pago que sí manda

- [x] 5.1 `PaymentStep` guarda el archivo y `StorefrontView` lo sube con el token que devuelve
      la creación del pedido — antes no hay pedido al que atarlo
- [x] 5.2 Una subida fallida se dice; no se pinta como enviada
- [x] 5.3 Pruebas: el comprobante viaja con el pedido; el fallo se enseña

## 6. Frontend — pagar la diferencia desde «mi pedido»

- [x] 6.1 Con saldo pendiente y método de prepago, ofrecer el mismo paso: método + comprobante
- [x] 6.2 Se enseña **lo que falta**, nunca el total del pedido
- [x] 6.3 Enviado ≠ pagado: la vista dice que espera confirmación y sigue mostrando el saldo
- [x] 6.4 En efectivo no se pide nada: se paga al recibir, como hoy
- [x] 6.5 Ofrecer TAMBIÉN mandarlo por el WhatsApp del negocio, al lado de adjuntar; sigue
      ofreciéndose cuando la subida falla, y no aparece si la sede no tiene teléfono
- [x] 6.6 Pruebas de las cinco frases de arriba

## 7. Frontend — el personal

- [x] 7.1 En la COMANDA, "comprobante por verificar" con la imagen, el monto declarado y la hora
- [x] 7.2 Aceptar es el mismo botón que verifica y manda a cocina; rechazar pide motivo
- [x] 7.3 Pruebas: un pedido sin declaración se verifica igual que hoy

## 8. Ajustes tras la primera prueba real

- [x] 8.a **Bug**: en el checkout el adjunto no hacía nada. El `<input>` vive dentro de un
      `v-for`, y ahí Vue convierte el template ref en un ARRAY: `fileInput.click()` no existía y
      el clic se perdía en silencio. Ahora es un `<label for>` — abre el selector sin JS — y
      tiene prueba, porque el fallo era invisible (el botón se pintaba igual)
- [x] 8.b El QR deja de ser un cuadrito CSS: se sube en Perfil del negocio y se muestra en la
      carta para escanear. Vive en la marca de la apariencia, donde ya viven el logo y el banner,
      así que llega a la carta pública por el camino que ya existía — sin endpoint ni migración.
      Sin QR subido no se pinta un falso que no escanea
- [x] 8.c El comprobante también se puede mandar por WhatsApp desde el checkout (la sede expone
      su teléfono en `GET /storefront/branches`)
- [x] 8.d El aviso de "pago confirmado" lista qué compró, con precios y total: "confirmamos tu
      pago" a secas obliga al cliente a rebuscar en el chat qué pidió

## 8. Puertas de calidad

- [x] 8.1 Backend: `ruff` limpio, `mypy` 397 ficheros, **898 pytest** en verde; `alembic`
      up/down/up de la 0030 verificado en Postgres y sin deriva
- [x] 8.2 Frontend: lint, type-check, **660 unit** y build en verde
- [x] 8.3 Manual: pedir por transferencia adjuntando comprobante; verlo en el panel y verificar;
      añadir algo desde el enlace, mandar el comprobante de la diferencia y comprobar que el
      pedido NO se cocina hasta que una persona lo verifica
