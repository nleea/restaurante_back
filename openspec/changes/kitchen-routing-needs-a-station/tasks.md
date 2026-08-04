## 1. Ver el problema antes de bloquear nada

El orden importa: si la validación llega primero, el negocio descubre la regla cuando ya no puede
activar un plato y todavía no tiene dónde arreglarlo.

- [x] 1.1 Añadir la lectura de "productos sin estación de cocina" en el módulo kitchen, con su endpoint y permiso.
- [x] 1.2 Añadir pruebas de esa lectura, incluidos productos con variantes activas (que son los urgentes).

## 2. La pantalla que falta

- [x] 2.1 Añadir a la carta la asignación de estaciones de un producto: listar las de la sede, mapear y quitar.
- [x] 2.2 Permitir fijar el rol (≤60 chars) y la lista de tareas (≤10, ≤60 chars cada una) de cada mapeo, reusando `attachProduct`/`loadProductStations` del store, que ya existen sin uso.
- [x] 2.3 Dejar la sección en sólo lectura sin el permiso de configuración de cocina, para que cualquiera pueda ver dónde se prepara un plato.
- [x] 2.4 Marcar en la carta los productos sin estación —"no se puede vender hasta asignarle una"— y hacerlos encontrables sin abrir uno por uno.
- [x] 2.5 Añadir pruebas de componente: mapear, quitar, rol y tareas, sólo lectura sin permiso, y el aviso de producto sin estación.

## 3. Sin estación no se vende

- [x] 3.1 Exigir al activar una variante que su producto tenga al menos una estación, junto a la exigencia de receta que ya existe.
- [x] 3.2 Hacer que el error diga QUÉ falta y DÓNDE se arregla; un "no se puede" a secas manda a leer código.
- [x] 3.3 Dejar que desactivar siga sin exigir nada: sacar algo de la carta no puede estar bloqueado.
- [x] 3.4 Reflejar el motivo en la carta al intentar activar, en vez de un fallo genérico.
- [x] 3.5 Añadir pruebas: activar sin estación, activar sin receta, activar con las dos, y desactivar sin ninguna.

## 4. Quitar la última estación no deja un plato vendible e inservible

- [x] 4.1 Permitir quitar el último mapeo: esas variantes caen en la banda roja de "no llegan a la cocina", que ya las incluye por diseño. Sin mecanismo nuevo.
- [x] 4.2 Añadir pruebas del camino elegido.

## 5. Enrutar deja de mentir

- [x] 5.1 Hacer que enrutar no reporte como enviado un ítem que no generó ningún ticket, e identificarlo.
- [x] 5.2 Decidir entre negar la comanda entera o enrutar el resto dejando constancia (pregunta abierta del diseño), y dejar dicho el porqué en el código.
- [x] 5.3 Añadir pruebas del ítem sin estación, y de que un pedido mixto no queda a medias en silencio.

## 6. Los platos que ya están así

- [x] 6.1 Auditado: `La Torre` (2 variantes activas, desde el 11 jul) y `Big Bang` (1). Ambos siguen vendiéndose.
- [x] 6.2 Sin migración que apague nada: aparecen en la banda roja de la carta y sus variantes siguen activas. Con prueba que lo fija.
- [x] 6.3 Auditados: **6 pedidos** con ítem sin ticket, **5 ya cerrados** (4 de La Torre, 1 de Big Bang). Reportados al negocio; no se reescribe ninguno.

## 7. Cierre

- [ ] 7.1 Correr las suites de backend y frontend, lint y tipos.
- [ ] 7.2 Comprobar a mano el camino completo: crear un plato, ver que no se puede activar, asignarle estación, activarlo, pedirlo por la carta y verlo aparecer en el KDS.
