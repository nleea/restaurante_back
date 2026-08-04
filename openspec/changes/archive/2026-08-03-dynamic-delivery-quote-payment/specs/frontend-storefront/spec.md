## ADDED Requirements

### Requirement: Delivery checkout communicates deferred quotation
The public storefront SHALL collect the delivery address or GPS point without displaying a fixed
delivery charge or requiring a payment method. Before submission it SHALL state that the delivery
cost and payment link will be confirmed by WhatsApp; after success it SHALL distinguish a pending
quote from a confirmed payable total.

#### Scenario: Customer orders delivery from the public menu
- **WHEN** a customer reaches the checkout for a delivery order
- **THEN** they can submit contact, products and location without selecting a payment method or
  seeing the obsolete fixed fee

#### Scenario: Confirmation awaits quote
- **WHEN** a delivery order is accepted but has not yet been quoted
- **THEN** the confirmation tells the customer that the final total and payment link will arrive
  after the delivery value is calculated
