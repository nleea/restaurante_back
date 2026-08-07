> Lee `design.md`. El change es **una línea de cálculo y una migración de datos**, y el riesgo está
> entero en la migración: toca `recovery_buffer` sólo de `low_stock`. Si toca las otras dos reglas,
> les cambia el significado a minutos y a puntos porcentuales que sí estaban bien.

## 1. Backend — el cálculo

- [x] 1.1 `LowStockEvaluator`: la condición pasa a `stock.current > stock.minimum * (1 +
      rule.recovery_buffer / 100)`
- [x] 1.2 Reescribir el comentario de esa línea: el colchón es un **porcentaje del mínimo** porque
      cada insumo tiene su unidad de medida y una cantidad fija significaría algo distinto para
      cada uno. Sin esa explicación, el siguiente lector devuelve la suma
- [x] 1.3 `DEFAULT_RECOVERY_BUFFER` de `1` a `10`, con el comentario diciendo que ahora es `%`
- [x] 1.4 Pruebas con los dos extremos que hoy fallan: mínimo 2 cierra en 2,3 (hoy exigía 3,1);
      mínimo 500 NO cierra en 501 (hoy sí, y no protegía de nada)
- [x] 1.5 Prueba de que reponer EXACTAMENTE al mínimo no cierra: la condición que disparó sigue
      siendo verdad
- [x] 1.6 Prueba de que un insumo con mínimo 0 sigue sin disparar (ya se salta antes, pero es la
      entrada por la que un porcentaje se volvería 0)

## 2. Backend — la migración

- [x] 2.1 Migración `0036`: `UPDATE alert_rules SET recovery_buffer = 10 WHERE rule_key =
      'low_stock'` y `server_default` de la columna a `10`
- [x] 2.2 **Sólo `low_stock`.** El docstring tiene que decir por qué no se convierte el valor viejo
      (design §3) y por qué no se tocan las otras reglas
- [x] 2.3 Anotar en el docstring que revertir exige devolver también el `UPDATE`: es el único punto
      del change donde el rollback no es gratis
- [x] 2.4 Prueba de que una regla de otra clave conserva su colchón tras migrar

## 3. Backend — no romper las otras reglas

- [x] 3.1 Repasar que `recovery_buffer` sigue leyéndose en minutos en la caja abierta y en puntos
      porcentuales en la cuota del asistente
- [x] 3.2 Pruebas de esas dos reglas sin tocar, para probar que el cambio está acotado

## 4. Frontend

- [x] 4.1 La pantalla de reglas pinta la unidad del colchón de cada regla: `%`, minutos o puntos
- [x] 4.2 Decirlo en palabras en el stock bajo: "la alerta se cierra cuando el stock supera el
      mínimo en ese porcentaje"
- [x] 4.3 Pruebas de que cada regla enseña su unidad

## 5. Cierre

- [x] 5.1 Actualizar el docstring de `evaluators.py`: la histéresis del stock bajo ya no se mide
      "en kilos"
- [x] 5.2 Puertas verdes: `ruff`, `mypy`, suite de backend, `vitest`, `type-check` y `eslint`
