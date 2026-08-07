## Why

`qr-table-ordering` dejó la mesa con un código público y la URL funcionando, pero el papel fuera
de alcance. Sin papel la capacidad no existe: un comensal no puede escanear una URL que sólo vive
en la base de datos.

Y el papel tiene una propiedad que ningún otro enlace del sistema tiene: **se imprime**. Un enlace
de WhatsApp mal construido se corrige mandando otro; una calcomanía mal construida hay que
despegarla de diez mesas, y el error no se descubre hasta que un cliente la escanea sentado. Eso
es lo que decide todo el diseño: la URL se construye en un solo sitio, y quien va a imprimir tiene
que poder LEER a dónde apunta sin escanear.

## What Changes

- **La URL de la mesa vive con los demás enlaces públicos.** `shared/links.table_order_url`, junto
  a `order_edit_url` y `delivery_payment_url`, y con el mismo contrato: sin dominio configurado,
  cadena vacía.
- **El QR de una mesa.** `GET /orders/tables/{table_id}/qr` devuelve `{url, svg}`. La URL viaja al
  lado del dibujo a propósito: un QR es opaco, y si la única forma de saber a dónde apunta fuera
  escanearlo, nadie comprobaría nada antes de mandar a imprimir.
- **SVG, no PNG**, y **corrección de errores ALTA**. Una calcomanía se amplía a 12 cm y vive
  pegada a una mesa que se mancha y se raya.
- **Falla en vez de imprimir basura.** Sin `STOREFRONT_BASE_URL`, sin código de sede o sin código
  de mesa, el endpoint responde 422 con el motivo. Un QR sobre una base vacía sería perfectamente
  legible y llevaría a ninguna parte.
- **Sin permiso nuevo**: `orders.read`. El código de la mesa no es un secreto —va impreso a la
  vista de cualquiera que entre—, así que lo que se protege es el acceso al panel, no el dato.
- **Dependencia**: `segno` (Python puro, sin dependencias nativas).

## Capabilities

### New Capabilities
- `table-qr-admin`: la URL pública de una mesa y su QR imprimible.

## Impact

- **Base de datos**: ninguna. El código de mesa ya existe (`qr-table-ordering`).
- **Backend**: `shared/links`, `orders` (dominio, caso de uso, API), `pyproject` (`segno`).
- **Pendiente**: la hoja imprimible con las N mesas juntas desde el Salón. Este cambio entrega la
  pieza por mesa; la hoja es UI y va después.
