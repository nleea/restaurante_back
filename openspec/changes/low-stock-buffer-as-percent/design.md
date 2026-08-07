## Context

`LowStockEvaluator` resuelve con `stock.current > stock.minimum + rule.recovery_buffer`. El
comentario que lo acompaña es correcto —"volver justo al mínimo no re-arma: al primer gramo que
salga volvería a disparar"— y el **número no tiene unidad**, porque el sujeto de esta regla es el
insumo y cada insumo tiene su `unit_of_measure_id`.

El colchón es lo único de esta regla que sí necesita saber en qué se mide, y es justo lo que no lo
sabe. El resultado es un parámetro que no se puede configurar bien: ajustarlo para el camarón lo
rompe para la sal.

## Goals / Non-Goals

**Goals:**

- Que el colchón signifique lo mismo para todos los insumos, midan lo que midan.
- Que el valor por defecto sea razonable sin que nadie lo toque.
- Conservar la histéresis, que sigue siendo necesaria.

**Non-Goals:**

- **Tocar el colchón de las otras dos reglas.** Ahí la unidad es única por regla.
- **Un colchón por insumo.** Es el segundo umbral que esta regla evita por diseño.
- **Sustituir la histéresis por una ventana de tiempo.** Ver "Alternativas".

## Decisions

### 1. Porcentaje del mínimo

```
antes:  stock > mínimo + colchón          ← "1" de kilos, gramos o unidades
ahora:  stock > mínimo × (1 + colchón/100)
```

Un porcentaje **no tiene unidad por construcción**, que es exactamente la propiedad que faltaba. Y
escala con el insumo sin que nadie lo configure: el 10% de 2 kg son 200 g y el 10% de 500 g son
50 g, y las dos cifras son razonables para su producto.

`0` sigue prohibido, igual que hoy: 0% es resolver justo por encima del mínimo, y al primer consumo
vuelve a disparar. La invariante no cambia, sólo la unidad en la que se expresa.

### 2. Diez por ciento

Es un margen que se nota sin ser exigente. Con mínimo 2 cierra en 2,2; con mínimo 100, en 110.

**Deja de ser cierto que "reponer al mínimo justo" cierre la alerta**, y eso es deliberado: al
mínimo justo, la condición que disparó sigue siendo verdad (`current <= minimum`), y resolver ahí
sería contradecirse dentro de la misma evaluación.

### 3. Los valores existentes se normalizan, no se convierten

La migración pone `10` en las filas de `low_stock`, sea cual sea su valor actual.

**Por qué no convertir:** un `1` que significaba "una unidad de algo" no tiene traducción a un
porcentaje — depende del mínimo de cada insumo, y la regla es por sucursal, no por insumo. Cualquier
fórmula de conversión inventaría una precisión que el dato no tiene. Y nadie pudo haberlo
configurado con intención, porque no había forma de saber qué significaba: normalizar es más
honesto que arrastrar el error con otra cara.

Se toca **sólo** `rule_key = 'low_stock'`. Las otras dos reglas conservan su valor porque el suyo sí
significaba algo.

### 4. La pantalla dice la unidad

Cada regla declara en qué mide su colchón: `%` para el stock bajo, minutos para la caja abierta,
puntos porcentuales para la cuota del asistente. La pantalla lo pinta al lado del campo.

Esto no es cosmético: **el defecto de origen es un número sin unidad en una pantalla que no la
decía.** Arreglar el cálculo y dejar la pantalla igual deja el mismo agujero abierto para el
siguiente parámetro.

## Alternativas consideradas

- **Ventana de tiempo en vez de cantidad** (tras resolverse, no puede volver a disparar en N
  minutos). Es unidad-agnóstica igual y además protege de saltos grandes, que un margen relativo no
  —un insumo que sube y baja un 50% parpadea igual—. Se descarta **por ahora** porque es un
  mecanismo nuevo, con columna nueva y su propio modo de fallo, para un problema que el porcentaje
  resuelve con una línea. Si el parpadeo aparece de verdad, ése es su change.
- **Colchón absoluto pero por unidad de medida** (1 kg, 100 g, 5 unidades). Tabla de conversión
  nueva y una decisión por cada unidad que alguien dé de alta. Más maquinaria y peor resultado que
  un porcentaje.

## Risks / Trade-offs

- **Un insumo con mínimo muy alto se vuelve más exigente que hoy** (mínimo 100: cierra en 110 en
  vez de 101) → correcto: 1 sobre 100 nunca fue un margen, era ruido de redondeo.
- **Un insumo con mínimo muy bajo se vuelve menos exigente** (mínimo 2: 2,2 en vez de 3) → correcto,
  y es el caso que motivó esto.
- **Un mínimo de 0 haría el colchón 0** → no puede llegar: el evaluador ya salta los insumos con
  `minimum <= 0` antes de nada, porque sin mínimo no pueden estar bajos.
- **Normalizar pisa un valor que alguien hubiera puesto a mano** → asumido y explicado (decisión 3):
  ese valor no podía ser correcto.

## Migration Plan

1. Migración `0036`: `UPDATE alert_rules SET recovery_buffer = 10 WHERE rule_key = 'low_stock'`, y
   `server_default` de la columna a `10`.
2. Efecto inmediato en el barrido siguiente: las alertas abiertas se evalúan con el margen nuevo.
3. **Rollback**: revertir el código devuelve la suma absoluta; los valores quedan en `10`, que como
   cantidad absoluta es un colchón grande. Si se revierte, hay que devolver también el `UPDATE`.
   Se dice aquí porque es el único punto del change en el que revertir no es gratis.

## Open Questions

Ninguna.
