## Why

Dos callejones sin salida dejan al operador sin forma honesta de seguir. Cancelar una comanda
libera su mesa pero abandona su entrega: se queda `pending` para siempre, nunca podrá llegar a
cocina porque la comanda ya no existe, y **bloquea el cierre de caja** de su turno. Hay dos así en
la base hoy. Y en la verificación de un prepago, el atajo a la conversación de WhatsApp dejó de
aparecer justo cuando más falta hace — cuando el cliente dice que pagó y no adjunta nada.

## What Changes

- Cancelar una comanda resuelve la entrega que **nunca salió**, con un estado terminal nuevo y
  propio: `cancelled`. Una entrega ya `assigned` o `in_transit` NO se toca — el domiciliario salió
  con la comida y el desenlace es suyo.
- Cerrar una comanda con una entrega sin resolver deja de ser un camino silencioso hacia una
  entrega inmortal.
- `cancelled` cuenta como **resuelta** en todo lo que hoy pregunta "¿está resuelta?": el bloqueo de
  cierre de caja, el resumen de pendientes y el histórico de sesión.
- Las dos entregas huérfanas existentes se resuelven con una migración de datos, sin tocar las que
  sí tuvieron un desenlace real.
- La verificación de un prepago ofrece ir a la conversación de WhatsApp cuando **ninguna
  declaración pendiente trae comprobante** — hoy la condición es "ninguna declaración", que la
  página de pago volvió falsa.

## Capabilities

### New Capabilities

Ninguna. Los dos problemas viven en capacidades existentes.

### Modified Capabilities

- `delivery-management`: el ciclo de vida gana un tercer estado terminal, `cancelled`, alcanzable
  sólo desde `pending` y sólo por la cancelación de su comanda.
- `order-management`: cancelar una comanda resuelve su entrega no despachada, igual que ya libera
  su mesa; cerrarla no puede dejarla sin desenlace.
- `cash-management`: una entrega `cancelled` está resuelta y no bloquea el cierre ni aparece como
  pendiente.
- `frontend-delivery-settlement`: la verificación de un prepago lleva a la conversación cuando no
  hay comprobante que mirar, porque "ya pagué" sin adjunto significa que está en el chat.

## Impact

- **Backend**: `orders` (cancelar/cerrar, puerto `DeliveryDispatch`), `delivery` (estado terminal,
  `D_TERMINAL`), `cash` (predicado de sin-resolver), `reports` (el mismo predicado en el histórico
  de sesión), migración de datos para las huérfanas.
- **Frontend**: la condición del atajo en el bloque de verificación de Salón; las etiquetas del
  tablero de despacho y de la vista del domiciliario para el estado nuevo.
- **Riesgo concreto**: el predicado "sin resolver" está escrito **tres veces** (caja, reportes y el
  propio `D_TERMINAL`). Olvidar uno deja el bloqueo puesto y el síntoma reaparece idéntico.
- Sin cambios de API pública ni de contrato con el cliente.
