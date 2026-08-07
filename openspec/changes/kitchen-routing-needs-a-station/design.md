## Context

Enrutar una comanda recorre sus ítems, resuelve el producto de cada variante y crea un ticket por
cada estación configurada para ese producto. Un producto sin estaciones produce una lista vacía, el
bucle no itera, y `route_order` devuelve `[]`. Nada falla: el pedido queda cobrado, `kitchen_state`
se queda en `none`, y la comida no existe para nadie.

Ese silencio **está especificado hoy**: el requisito dice literalmente que un ítem cuyo producto no
tiene estación no produce ticket. No es un descuido, es la regla — y tiene una razón plausible
detrás, la de que una bebida embotellada no necesita cocina.

El problema es que el sistema no puede distinguir esas dos cosas:

```
producto sin estación
   ├── "no lleva cocina"       → correcto no crear ticket
   └── "nadie lo configuró"    → pedido cobrado que nadie prepara
```

Y resuelve la ambigüedad siempre hacia el primer lado, que para comida es el peligroso.

En la práctica el negocio ya trabaja como si todo producto tuviera estación: los platos sembrados
tienen entre una y tres, existe una estación **Bebidas**, y los únicos dos sin asignar son los dos
que se crearon después de que la pantalla dejara de existir — o más bien, sin que llegara a existir.

## Goals / Non-Goals

**Goals:**

- Que no se pueda vender un plato que nadie va a cocinar.
- Que asignar la estación sea posible desde la interfaz, que es lo que hoy falta.
- Que el negocio vea qué productos le faltan por configurar antes de que lo descubra un cliente.
- Que los platos ya activos sin estación se traten de forma deliberada, no por efecto colateral.

**Non-Goals:**

- Cambiar cómo el KDS reparte, agrupa o muestra los tickets una vez creados.
- Tocar los pedidos ya cobrados: el daño hecho se identifica, no se reescribe.
- Inventar un concepto de "producto que no pasa por cocina". Justo lo contrario — ver abajo.

## Decisions

### Sin estación no se vende, en vez de un campo "no lleva cocina"

La alternativa era marcar el producto como exento. Se descarta: añade un concepto que hay que
entender y mantener, y deja intacto el fallo de origen — un plato mal marcado vuelve a ser
invisible en silencio, que es exactamente lo que pasó.

Exigir estación elimina la ambigüedad sin inventar nada. Una bebida va a la estación **Bebidas**,
que ya existe: alguien la saca de la nevera y la entrega, y eso ES una tarea de preparación. El
modelo pasa a decir algo verdadero — todo lo que se vende, alguien lo prepara — en vez de tener una
categoría de cosas que aparecen solas.

Encaja además con los datos reales: sólo dos productos quedan fuera, y son precisamente los dos que
hay que arreglar.

### Es la misma regla que ya rige las recetas, y se escribe igual

`menu-product-variants` ya dice que una variante no se activa sin al menos un ítem de receta, y que
una variante nueva nace inactiva. Este requisito es de la misma clase: configuración sin la cual
vender es una promesa que el negocio no puede cumplir.

Se implementa en el mismo sitio y con la misma forma —una condición más para activar— en lugar de
un mecanismo aparte. Desactivar sigue siendo siempre posible y no exige nada: sacar algo de la
carta nunca puede estar bloqueado.

La diferencia con la receta merece decirse: la receta es del **variante** y la estación es del
**producto**, así que activar una variante mira una cosa que sus hermanas comparten. Es correcto —
el producto es lo que se cocina; el tamaño no cambia quién lo prepara.

### Enrutar deja de ser el sitio donde se descubre el problema

Con la regla anterior, un ítem sin estación no debería poder existir en una comanda. Pero
"no debería" no es "no puede": quedan los pedidos ya tomados y cualquier camino que active algo
sin pasar por la validación.

Así que enrutar deja de tratar el caso como normal. Qué hace exactamente —negarse, o crear lo que
pueda y reportar lo que no— se decide al implementar; lo que no se acepta es que siga devolviendo
éxito con cero tickets. Un pedido que la cocina no ve tiene que ser ruidoso en algún sitio.

### Quitar la última estación se permite, y el plato cae en la banda roja

Negarlo protegería más, pero frustra a quien está reorganizando la cocina por una razón legítima
—una estación que se cierra, un plato que cambia de sitio— y le obliga a deshacer la venta antes
de poder mover nada.

Se permite, y esas variantes aparecen inmediatamente entre los platos que no llegan a la cocina.
No hace falta mecanismo nuevo: la lectura de "productos sin estación" ya incluye los que tienen
variantes activas, y precisamente por eso las pone primero. Quitar la última estación es entonces
visible en el mismo sitio donde se ve todo lo demás que falta configurar.

El coste asumido: entre que se quita y alguien mira la banda, ese plato se puede pedir. Es el
mismo riesgo que ya existe con un plato recién creado, y se paga a cambio de no bloquear una
reorganización.

### Los platos ya activos sin estación no se apagan solos

La regla nueva los deja fuera, pero desactivarlos en el despliegue sacaría dos platos de la carta
sin que nadie lo pida y sin que el dueño se entere hasta que un cliente pregunte.

Se hacen **visibles** y se deja la decisión al negocio: la carta señala qué productos no pueden
venderse todavía y por qué. Una migración que apaga cosas es más difícil de deshacer que una lista
que alguien resuelve en dos minutos.

### La asignación vive en la carta, no en una pantalla de cocina aparte

El momento en que hace falta es al crear el plato, y ahí es donde está la persona. Mandarla a otra
sección a completar la configuración es exactamente el paso que hoy no ocurre.

El mapeo lleva su rol y sus tareas, que ya están en el modelo y en el API; la pantalla los expone
en vez de obligar a un segundo sitio para lo mismo.

## Risks / Trade-offs

- [Un producto que de verdad no pasa por cocina se ve forzado a una estación] → la estación
  Bebidas cumple ese papel y refleja lo que pasa de verdad: alguien lo entrega. Si aparece un caso
  que no encaja, es señal de que hace falta una estación nueva, no una excepción.
- [La regla bloquea activar un plato a media configuración] → es el punto; pero el mensaje tiene
  que decir qué falta y dónde arreglarlo, no sólo negarse.
- [Dos platos activos quedan fuera de la regla] → se muestran en vez de apagarse, y el negocio
  decide. Ninguna venta pasada cambia.
- [Alguien vuelve a crear un camino que active sin validar] → por eso enrutar también deja de ser
  silencioso: la segunda red existe porque la primera es una regla de aplicación, no de base.

## Migration Plan

1. Añadir la lectura de "productos sin estación" y mostrarla en la carta: el negocio ve el problema
   antes de que ninguna regla lo bloquee.
2. Publicar la pantalla de asignación, para que haya cómo arreglarlo.
3. Activar la validación al activar variantes.
4. Hacer ruidoso el enrutado sin estación.
5. Rollback: revertir el código devuelve el silencio anterior; ninguna fila cambia de estado por
   este cambio, así que no hay nada que deshacer en datos.

## Open Questions

- ¿Qué debe hacer exactamente enrutar con un ítem sin estación — negar la comanda entera, o
  enrutar el resto y dejar constancia del que no pudo? Negar protege más y molesta más.

