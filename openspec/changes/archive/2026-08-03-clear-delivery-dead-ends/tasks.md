## 1. Un solo predicado de "resuelta"

Primero esto y sin cambiar comportamiento: con la lista de terminales copiada en tres sitios,
cualquier orden que empiece por añadir el estado deja un consumidor desalineado y el bloqueo puesto.

- [x] 1.1 Dar a los estados terminales de una entrega una definición única en el dominio de delivery, y hacer que `D_TERMINAL` la use.
- [x] 1.2 Hacer que el guard de cierre de caja y el resumen de pendientes (`cash`) deriven de esa definición en vez de su propio `notin_`.
- [x] 1.3 Hacer que el histórico de sesión (`reports`) derive de la misma definición.
- [x] 1.4 Añadir una prueba que falle si algún consumidor deja de coincidir con la definición única — es la que convierte "se me olvidó un sitio" en un fallo visible.

## 2. El estado terminal `cancelled`

- [x] 2.1 Añadir `cancelled` como tercer estado terminal de una entrega, rechazando cualquier transición que salga de él.
- [x] 2.2 Comprobar que las cifras de entregas fallidas siguen contando sólo `not_delivered`, con una prueba que lo fije.
- [x] 2.3 Añadir pruebas de que una entrega `cancelled` no bloquea el cierre de caja ni aparece en el resumen de pendientes.

## 3. Cancelar y cerrar sueltan la entrega

- [x] 3.1 Ampliar el puerto `DeliveryDispatch` (orders → delivery) con la liberación de la entrega de un pedido, e implementar su adaptador en delivery.
- [x] 3.2 Hacer que `cancel_order` libere la entrega que sigue en `pending`, junto a la liberación de la mesa que ya hace.
- [x] 3.3 Dejar intacta la entrega ya `assigned` o `in_transit`: su desenlace es del domiciliario que salió con la comida.
- [x] 3.4 NO hacerlo en `close_order`: cerrar significa que la comanda está pagada y sigue a cocina y despacho, así que su entrega —en `pending`, esperando asignación— tiene que quedarse. Con prueba que fija la distinción.
- [x] 3.5 Verificar que sin adaptador enchufado cancelar y cerrar siguen funcionando igual que hoy (un despliegue sin domicilios).
- [x] 3.6 Añadir pruebas: cancelar con entrega `pending`, con entrega despachada, y cancelar un pedido que no es domicilio.

## 4. Las huérfanas que ya existen

- [x] 4.1 Escribir la migración de datos que resuelve sólo las filas con comanda `cancelled`, entrega `pending` y sin `delivered_at`.
- [x] 4.2 Hacer el `downgrade` explícito sobre que no revive nada: devolverlas a `pending` reintroduciría el bloqueo.
- [x] 4.3 Correr la migración y comprobar que las 2 huérfanas de la base quedan resueltas y que ninguna entrega con desenlace real cambió.

## 5. Las pantallas conocen el estado nuevo

- [x] 5.1 Añadir `cancelled` a las etiquetas y estilos del tablero de despacho, para que no salga el literal crudo.
- [x] 5.2 Añadir `cancelled` a la vista del domiciliario (píldora de estado, rail de paradas, historial del día).
- [x] 5.3 Sacar del tablero de despacho las entregas `cancelled`: el tablero es una lista de trabajo, y una cancelada no le pide nada a nadie.

## 6. El atajo al chat en la verificación

- [x] 6.1 Cambiar la condición del atajo en el bloque de verificación de Salón: mostrarlo cuando ninguna declaración pendiente traiga comprobante y la comanda tenga contacto de WhatsApp.
- [x] 6.2 Añadir pruebas de los cuatro casos: sin declaración, declaración sin comprobante, declaración con comprobante, y sin contacto vinculado.
- [x] 6.3 Decir en la comanda CÓMO va a pagar cuando no hay nada que verificar: efectivo ("cobra en la puerta, puedes mandarlo a cocina") y domicilio sin método elegido ("lo elige desde el enlace"). Sin esto los dos casos se ven idénticos —un botón de cocina y nada más— y se deciden igual.

## 7. Cierre

- [x] 7.1 Confirmado: `cancel_order` ya manda `CUSTOMER_STATE_CANCELLED` y el autoreply tiene su plantilla. No hace falta aviso nuevo.
- [x] 7.2 Suites en verde (1229 backend / 929 frontend), lint limpio y sin errores de tipos nuevos.
- [x] 7.3 Comprobado a mano el 2026-08-03: cancelar saca el domicilio del tablero, cerrar lo deja esperando despacho, y la comanda dice cómo va a pagar.
