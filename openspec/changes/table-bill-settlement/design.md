## Context

Lo que ya sostiene el dinero, y que este cambio se niega a duplicar:

| Hecho | Dónde |
|---|---|
| `OrderPayment` cuelga de un `order_id` | `orders/domain/entities.py` |
| Registrar un pago escribe pago + movimiento de caja **atómicamente** | `register_payment` |
| Un pago exige sesión de caja abierta | mismo sitio |
| `close_order` exige `payments_total >= total`, o cliente para fiar | `manage_orders.py` |
| Sobrepago es vuelto y cierra normal | mismo sitio |
| El cierre descuenta inventario y es idempotente | `consume_inventory_for_order` |
| La mesa se libera sólo si no queda comanda abierta | `qr-table-ordering` |
| `receipt_prints` es auditoría de impresiones, no documento | `record_receipt_print` |

`payments_total` es hoy **la única verdad** de si una comanda está pagada, y de ella cuelgan el
cierre, el arqueo, el reporte Z y las devoluciones. Cualquier diseño que introduzca una segunda
noción de «pagado» tiene que reconciliarse con ésa para siempre.

## Goals / Non-Goals

**Goals:**
- Que cobrar la mesa 5 completa sea **un** gesto del cajero, no tres.
- Que separar sea el mismo gesto con menos miembros, no otro mecanismo.
- Que ninguna comanda quede cerrada sin estar cubierta, ni cobrada dos veces.
- Que el cliente se lleve un papel que dice la verdad sobre lo que es.

**Non-Goals:**
- Factura electrónica. Cambio aparte, calendario aparte, proveedor aparte.
- Repartir un plato entre comensales. Quien lo pidió lo paga.
- Cuentas entre mesas o mover una comanda de mesa.
- Que el cliente pague desde su celular. Se paga en caja; el enlace del comensal sigue siendo para
  ver y añadir, no para cobrar.
- Propinas. No existen hoy y añadirlas aquí mezclaría dos discusiones.

## Decisions

### 1. La cuenta de mesa es un agrupador, no una primitiva de dinero

`table_bills` agrupa comandas; el dinero sigue viviendo en `order_payments`.

*Por qué*: si la cuenta guardara su propio saldo habría dos respuestas a «¿está pagado?» —la de la
cuenta y la de `payments_total`— y todo lo que ya lee la segunda (cierre, arqueo, Z, devoluciones)
tendría que aprender la primera. Un agrupador no puede desincronizarse de nada porque no afirma
nada sobre dinero.

*Corolario que importa*: **`close_order` no se toca.** Cada comanda llega al cierre con sus pagos
cubriendo su total, de verdad, no por excepción. La regla que hizo desaparecer ventas de la caja
—cerrar sin pagar— sigue intacta y sin agujeros nuevos.

### 2. El reparto es en cascada, no a prorrata

Un pago de la cuenta se asigna a las comandas miembro por antigüedad, llenando cada una hasta su
total antes de pasar a la siguiente.

```
  Ana $32.000   Luis $54.000   Sofía $34.000      cuenta: $120.000
  pago 1: efectivo $120.000
    → Ana  32.000  (cubierta)
    → Luis 54.000  (cubierta)
    → Sofía 34.000  (cubierta)

  pago 1: tarjeta $80.000   pago 2: efectivo $40.000
    → Ana  32.000 tarjeta
    → Luis 48.000 tarjeta + 6.000 efectivo   ← una comanda, dos métodos: ya se sabe hacer
    → Sofía 34.000 efectivo
```

*Por qué cascada y no prorrata*: la prorrata parte cada pago en pedazos que nadie pidió, produce
centavos que hay que redondear y deja devoluciones ilegibles («devolver $17.333 del pago de
tarjeta»). La cascada produce importes que un humano reconoce, y una comanda con dos métodos ya es
un caso que el sistema sabe manejar hoy.

*El sobrante es vuelto*, y se aplica a la última comanda cubierta: la regla de sobrepago ya existe y
ya lo trata como vuelto.

*Determinismo*: el orden es `created_at`, y `id` para desempatar. Sin él, dos cobros idénticos
producirían asignaciones distintas y los tests serían inestables.

### 3. Un pago de la cuenta escribe N movimientos de caja, y está bien

Cobrar la cuenta de la mesa 5 con un billete de $120.000 deja tres movimientos en el libro:
$32.000, $54.000 y $34.000.

*Por qué se acepta*: para el arqueo y el Z es la misma plata. Y el libro por comanda es lo que las
devoluciones y la conciliación ya entienden: devolver lo de Sofía es una operación sobre la comanda
de Sofía, no un despiece de un movimiento agregado. Un movimiento único de $120.000 sería más bonito
en el feed y más caro en todo lo demás.

*Lo que sí se le debe al cajero*: que el feed diga que esas tres líneas fueron un solo cobro. Eso es
presentación —las tres referencian la misma cuenta—, no un modelo nuevo.

### 4. Separar no es un modo: es una cuenta con menos miembros

Abrir la cuenta de una mesa preselecciona **todas** sus comandas abiertas. El cajero quita las que
no van. Pagar solo es una cuenta de un miembro.

*Por qué*: «junto» y «separado» como dos caminos distintos duplicarían el reparto, el cierre y la
tirilla, y obligarían a decidir qué pasa cuando la mesa se paga mitad y mitad. Con un único
mecanismo, «Ana y Luis juntos, Sofía aparte» son dos cuentas, y ninguna es un caso especial.

*Una comanda está en una sola cuenta abierta a la vez.* La pertenencia vive en
`orders.table_bill_id`, una columna escalar, así que apuntar a dos cuentas es imposible por
construcción. Lo que hay que impedir además es que una segunda cuenta RECLAME una comanda que ya
está en una abierta — dos cajeros con la misma mesa en pantalla es un escenario real.

**Corrección sobre la propuesta**: esto se escribió como "índice único parcial", y al
implementarlo resultó que no es expresable así. Un índice sobre `(id, table_bill_id)` es
trivialmente único porque `id` ya es la clave primaria: no garantiza nada. La reclamación se hace
con un UPDATE condicional —`SET table_bill_id = :bill WHERE id IN (...) AND table_bill_id IS
NULL`— comprobando cuántas filas cambiaron. Es atómico en la base, que es lo que se quería; la
comprobación previa en la aplicación queda como cortesía para dar un error legible.

### 5. Fiado se sale de la cuenta

Una cuenta se cobra completa. Si un comensal va a fiado, se quita de la cuenta y se cierra por el
camino de siempre —asignar cliente y cerrar con crédito—, que ya existe y ya funciona.

*Por qué no permitir fiado dentro del grupo*: obligaría a que el reparto sepa qué comandas pueden
quedar descubiertas y cuáles no, y a que el cierre en cascada aplique dos reglas distintas según el
miembro. Sacarla de la cuenta cuesta un toque y deja las dos reglas en su sitio.

### 6. La tirilla dice que no es una factura

`receipt_prints.order_id` pasa a nullable, se añade `table_bill_id`, y un CHECK exige exactamente
uno de los dos.

*Por qué no una tabla nueva*: la pregunta que responde la tabla —«¿esto ya se imprimió, es
reimpresión?»— es idéntica para una comanda y para una cuenta. Dos tablas para la misma pregunta se
desincronizan.

*Por qué no registrar la impresión de la cuenta como N impresiones de comanda*: haría que la
reimpresión de la cuenta marcara `is_reprint` en comandas que nunca se imprimieron solas, y
convertiría una auditoría honesta en ruido.

*Y por qué el papel se declara*: en Colombia un papel con nombre, NIT y total se parece mucho a un
documento fiscal, y no lo es. La tirilla lleva la frase que lo dice. El día que entre
`electronic-invoicing`, esa frase se sustituye por CUFE y QR, y el sitio donde va ya existe.

### 7. Qué pasa si la caja se cierra a media comida

El pago exige sesión abierta; ésa es la regla de hoy y no se toca. Una cuenta abierta cuya sesión se
cerró simplemente no se puede cobrar hasta que haya otra abierta, y el error que sale es el que ya
sale.

*Por qué no atar la cuenta a la sesión*: la comida dura más que un turno en un local que hace
almuerzo y cena. Atar la cuenta a la sesión en la que se abrió obligaría a inventar una migración de
cuentas entre turnos para un caso que la regla de pago ya resuelve sola.

## Risks / Trade-offs

- **El reparto toca dinero.** Es la parte peligrosa del cambio. Reparto y cierre en cascada van en
  **una** transacción: o quedan las tres cubiertas y cerradas, o no queda nada. Un fallo a mitad que
  deje a Ana cerrada y a Sofía cobrada sin cerrar es el peor resultado posible y hay que probarlo
  explícitamente, no confiarlo.
- **Dos cajeros, una mesa.** La defensa real es el UPDATE condicional con recuento de filas
  (§4); la comprobación en la aplicación es cortesía para dar un error legible.
- **Una comanda crece después de abrir la cuenta.** Ana pide un café mientras el cajero cobra. El
  total de la cuenta se recalcula al cobrar, no al abrir: la cuenta guarda miembros, no un importe
  congelado. El `total` de la tabla es el del momento del cobro.
- **El feed de caja se alarga.** Tres líneas donde antes hubiera ido una. Aceptado en §3.
- **La tirilla no es factura.** Un cliente que pida factura se va sin ella. Es una limitación
  conocida y declarada, no un descuido: está anotada como deuda con su propio cambio.

## Migration Plan

`0046_table_bills.py`:

1. Crear `table_bills`.
2. `orders.table_bill_id` nullable + FK `ON DELETE SET NULL` + índice único parcial sobre
   `table_bill_id` donde la cuenta esté abierta, de forma que una comanda no pueda estar en dos.
3. `receipt_prints.table_bill_id` nullable + FK; `receipt_prints.order_id` pasa a nullable; CHECK
   `(order_id IS NULL) <> (table_bill_id IS NULL)`. Las filas existentes ya cumplen el CHECK.
4. `downgrade`: quitar CHECK, devolver `order_id` a no-nulo (las filas de cuenta se borran antes),
   quitar columnas y tabla.
5. Verificar `upgrade` → `downgrade -1` → `upgrade` contra Postgres con impresiones preexistentes.

## Open Questions

- ¿La tirilla se imprime desde el navegador (CSS de impresión, como el Reporte Z) o hay una
  impresora térmica con la que haya que hablar? Este cambio asume lo primero, que es lo que el
  proyecto ya hace en otros sitios; una térmica de verdad es otro cambio y otro protocolo. RT: una termica
- ¿El cajero puede reabrir una cuenta ya cobrada para corregir un error? Por ahora no: se corrige
  con el camino de devolución que ya existe, por comanda. Si en la práctica duele, se revisa con
  datos.: no no se puede reabrir 
