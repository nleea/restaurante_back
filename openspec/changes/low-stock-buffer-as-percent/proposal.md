## Why

El colchón de recuperación del stock bajo es **un número sin unidad**. La condición es
`stock > mínimo + colchón`, con el colchón en `1` por defecto, y ese `1` se aplica igual sobre
kilos de camarón, gramos de sal y unidades de huevo — porque el sujeto de esta regla es el insumo,
y **cada insumo tiene su propia `unit_of_measure_id`**.

| insumo | mínimo | colchón `1` significa | efecto |
|---|---|---|---|
| Camarón (kg) | 2 kg | 1 **kilo** entero | hay que reponer un 50% de más para que cierre |
| Sal (g) | 500 g | 1 **gramo** | el colchón no protege de nada |
| Huevos (ud) | 24 | 1 **unidad** | pasable, por casualidad |

No existe ningún valor que sea correcto para los tres a la vez: es un parámetro mal dimensionado,
y la consecuencia práctica es que **nadie puede configurarlo bien**. Quien lo ajusta para que el
camarón se comporte lo rompe para la sal, y al revés. Ya costó un rato de depuración creyendo que
había un fallo donde había un desbalance.

## What Changes

- **El colchón del stock bajo pasa a ser un porcentaje del mínimo**, no una cantidad. La condición
  de recuperación es `stock > mínimo × (1 + colchón/100)`.
- **Un porcentaje es unidad-agnóstico por construcción**, que es la razón entera del change: el
  10% de 2 kg son 200 g y el 10% de 500 g son 50 g, y las dos cosas son igual de razonables sin que
  nadie tenga que pensar en la unidad.
- **Por defecto 10%.** Con mínimo 2 kg cierra al pasar de 2,2 kg; con mínimo 500 g, de 550 g.
- **Los valores actuales se normalizan a ese 10%** en la migración. No se conservan: un `1` que
  significaba "una unidad de algo" no tiene traducción honesta a un porcentaje, y fingir que la
  tiene sería arrastrar el error.
- **Sigue prohibido el cero**, como hoy: 0% es resolver justo por encima del mínimo, que es
  exactamente el parpadeo que la histéresis existe para impedir.
- **Las otras dos reglas no se tocan.** La caja abierta lee el colchón en minutos y la cuota del
  asistente en puntos porcentuales; ahí la unidad es única por regla y el número significa algo.
- **La pantalla de reglas dice la unidad de cada colchón** — `%`, minutos o puntos según la regla.
  El defecto de origen es un número sin unidad en una pantalla que no la decía.

## Capabilities

### Modified Capabilities

- `alert-notifications`: el colchón de recuperación del stock bajo se interpreta como porcentaje
  del mínimo; la histéresis deja de estar expresada en la unidad del sujeto.
- `frontend-alerts`: la pantalla de reglas presenta el colchón con la unidad que le corresponde a
  cada regla.

## Impact

- **Backend `alerts`**: una línea de `LowStockEvaluator` y su comentario; `DEFAULT_RECOVERY_BUFFER`
  pasa de `1` a `10`.
- **Migración 0036**: normaliza `alert_rules.recovery_buffer` a `10` **sólo** en las filas de
  `low_stock`, y mueve el `server_default` de esa columna. Las otras reglas quedan intactas.
- **Cambio de comportamiento**: las alertas de stock bajo cierran con un margen relativo en vez de
  absoluto. Para un insumo con mínimo alto se vuelve más exigente que hoy (mínimo 100 → cierra en
  110 en vez de 101); para uno con mínimo bajo, menos (mínimo 2 → 2,2 en vez de 3). Las dos
  direcciones son el arreglo: hoy el margen no guardaba relación con lo que se mide.
- **Sin permiso nuevo, sin endpoint nuevo, sin columna nueva.**
- **No rompe nada**: ninguna alerta se pierde y ninguna se dispara de más; sólo cambia el punto en
  el que una abierta se declara recuperada.

## Notes

Fuera de alcance:

- **Un colchón por insumo.** Sería el margen exacto de cada producto y es precisamente el segundo
  umbral que `LowStockEvaluator` se escribió para no introducir: inventario ya lleva `min_stock`, y
  dos umbrales para un concepto divergen en un mes.
- **Cambiar la histéresis a una ventana de tiempo.** Se consideró (protege también de saltos
  grandes, que el margen relativo no) y se descarta por ahora: es un mecanismo nuevo con su propia
  columna y su propio modo de fallo, y el problema que hay sobre la mesa es la unidad.
