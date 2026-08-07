## 1. La URL, en un solo sitio

- [x] 1.1 `table_order_url` en `shared/links.py`, junto a `order_edit_url` y `delivery_payment_url`, con el mismo contrato de "sin dominio, cadena vacía"
- [x] 1.2 Percent-encoding de los dos códigos, aunque hoy sean alfanuméricos
- [x] 1.3 Tests de la función pura: forma, subdominio del tenant, sin dominio, códigos con barra

## 2. El dibujo

- [x] 2.1 Dependencia `segno` (Python puro, sin dependencias nativas)
- [x] 2.2 `table_qr_svg` en `orders/domain/table_qr.py`: función pura, SVG, corrección de errores ALTA, zona tranquila de 4 módulos
- [x] 2.3 Revienta ante una URL vacía en vez de codificar un QR que lleva a ninguna parte
- [x] 2.4 Tests: es SVG, rechaza vacío, el nivel alto produce un dibujo más denso que el bajo

## 3. El endpoint

- [x] 3.1 `tenant_slug` y `branch_code` en el puerto y el repositorio de orders (`skip_tenant_filter` en `tenants`, que es la tabla DE los tenants)
- [x] 3.2 `OrderService.table_qr` devuelve `(url, svg)` y falla con motivo ante cada pieza que falte
- [x] 3.3 `storefront_base_url` inyectado desde el composition root, no leído dentro del caso de uso
- [x] 3.4 `GET /orders/tables/{table_id}/qr` gated por `orders.read` — sin permiso nuevo (evita el 403 universal de un permiso sin sembrar)
- [x] 3.5 Tests de API: 200 con url+svg, 422 sin dominio, 404 mesa desconocida, 403/401 sin permiso
- [x] 3.6 Prueba manual contra datos reales: la mesa 1 devuelve `…/store/MAIN/table/M63S94`

## 4. Pendiente (la hoja imprimible)

- [x] 4.1 Servicio y store del frontend para pedir el QR de una mesa
- [x] 4.2 Hoja imprimible con las N mesas de la sede, cada QR rotulado con su número (CSS de impresión, como el Reporte Z)
- [x] 4.3 La URL visible junto a cada QR, para poder comprobarla antes de mandar a imprimir
- [x] 4.4 Acceso desde el Salón, gated por `orders.read`
- [x] 4.5 Tests de componente
- [x] 4.6 Prueba manual: imprimir la hoja, pegar una calcomanía y escanearla con un teléfono
