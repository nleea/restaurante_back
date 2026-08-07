# frontend-orders-payments (delta)

## MODIFIED Requirements

### Requirement: Cobrar y cerrar with split payments and credit

Cobro SHALL live in the Comanda's payment sheet (the order ticket's payment panel is
retired). The user registers split payments per method (efectivo / tarjeta / nequi /
transferencia), the sheet shows paid / saldo / vuelto derived from the server total,
and closing follows the settlement gate. For fiado, the user assigns an **existing**
registered customer to the order (chosen from the customers directory; no inline
create) and then closes; the backend records the unpaid remainder as that customer's
credit. The chosen customer's current credit balance is shown as a reference when
picking.

#### Scenario: Register split payments then close

- **WHEN** the user registers one or more payments that together settle the order and closes it
- **THEN** the order closes and any overpayment is shown as vuelto

#### Scenario: Assign an existing customer and fiar

- **WHEN** a balance remains and the user picks an existing customer and chooses "Fiar y cerrar"
- **THEN** the client assigns the customer to the order, closes it, and the remainder becomes the customer's credit

#### Scenario: Pick surfaces the customer's current credit

- **WHEN** the user is choosing a customer to fiar
- **THEN** each candidate shows its current outstanding credit balance as a reference

#### Scenario: No inline customer creation

- **WHEN** the needed customer does not exist
- **THEN** cobro offers no inline create; a "Crear cliente" affordance routes to the Clientes view
