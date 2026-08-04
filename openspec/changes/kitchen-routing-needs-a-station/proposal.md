## Why

Un plato nuevo se puede vender, cobrar y cerrar sin que la cocina llegue a verlo. Pasó de verdad:
se creó "Big Bang", se pidió por la carta pública, se verificó el pago y se mandó a cocina — y en
el KDS no apareció nunca. Enrutar un ítem cuyo producto no tiene estación asignada crea **cero
tickets y no se queja**, así que el pedido queda cobrado y nadie lo prepara. Uno de esos dos
pedidos ya está cerrado.

La causa de fondo es que ninguna pantalla permite asignar la estación: la API existe y el store
del frontend también, pero nada los llama. Todo plato nuevo nace invisible para la cocina y no hay
forma de arreglarlo desde la interfaz.

## What Changes

- **BREAKING**: una variante deja de poder venderse si su producto no tiene ninguna estación de
  cocina asignada. La regla es la misma que ya rige las recetas: sin configurar, la variante no se
  activa, y una variante nueva nace inactiva.
- Enrutar deja de resolver en silencio la ausencia de estación. El sistema ya no tiene que
  adivinar si un producto "no lleva cocina" o "está sin configurar": si se vende, tiene estación.
- Nueva pantalla para asignar estaciones a un producto, con su rol y sus tareas, desde la carta.
  Es lo que faltaba de verdad — la API y el store ya estaban.
- La carta señala los productos que todavía no pueden venderse por no tener estación, en vez de
  dejar que se descubra cuando un cliente ya pagó.
- Los productos existentes sin estación quedan identificados para que el negocio los configure;
  ninguna venta pasada se altera.

## Capabilities

### New Capabilities

Ninguna. El problema vive entero en capacidades que ya existen.

### Modified Capabilities

- `menu-product-variants`: activar una variante exige además que su producto tenga estación de
  cocina, igual que ya exige receta.
- `kitchen-management`: enrutar deja de aceptar en silencio un ítem sin estación; el caso pasa a
  ser imposible por construcción y, si aun así ocurre, se hace visible.
- `frontend-menu`: la carta permite asignar estaciones a un producto y muestra cuáles no pueden
  venderse todavía.

## Impact

- **Backend**: la validación de activación en `menu`, el enrutado en `kitchen`, y una lectura que
  responda "¿qué productos no tienen estación?".
- **Frontend**: la carta (`/menu`) gana la asignación de estaciones; el store de cocina ya tiene
  `attachProduct` / `loadProductStations` sin usar.
- **Datos**: dos productos activos sin estación (`Big Bang`, `La Torre`) quedarían fuera de la
  regla nueva. Hay que decidir explícitamente qué pasa con ellos en vez de desactivarlos de
  golpe — un despliegue que apaga platos sin avisar es peor que el bug.
- **Permisos**: `menu.manage` para la carta, `kitchen.update` para el mapeo; no se crean permisos
  nuevos.
- Sin cambios en el contrato público de la carta ni en el flujo de pedido.
