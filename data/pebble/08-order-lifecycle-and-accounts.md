---
doc_id: POL-ORD-008
title: Order Lifecycle, Accounts and Cancellations
version: 2.1
effective_from: 2025-04-15
supersedes: 2.0 (2024-12-01)
owner: Customer Operations
---

# Order Lifecycle, Accounts and Cancellations

## 1. Order reference format

Every order receives a reference in the format `PB-nnnn`, where `nnnn` is four
digits, for example `PB-4471`. The reference is issued at checkout and appears
in the confirmation email within 5 minutes.

References are not sequential and carry no information about order date,
value, or contents. An agent cannot infer anything from the number itself and
must look the order up.

Returns receive a separate reference in the format `RMA-nnnnn`, five digits.
Repairs receive `REP-nnnnn`. A customer quoting a five-digit number is not
quoting an order reference.

## 2. Order states

| State | Meaning | Customer can still |
| --- | --- | --- |
| `PENDING` | Payment authorised, not yet released to the warehouse | Cancel, edit address, edit contents |
| `PICKING` | Warehouse is assembling the order | Nothing. Changes are no longer possible |
| `PACKED` | Boxed, awaiting carrier collection | Nothing |
| `DISPATCHED` | With the carrier, tracking issued | Request an intercept, chargeable |
| `DELIVERED` | Carrier has confirmed delivery | Return under POL-RET-001 |
| `CANCELLED` | Cancelled before dispatch, authorisation released | Reorder |
| `RETURNED` | Return received and inspected | — |
| `REFUNDED` | Money released back | — |

Orders normally sit in `PENDING` for around **one hour** during business hours.
Orders placed after the 15:00 GMT cut-off stay `PENDING` until the next
business morning, which is a wide and useful window for changes.

## 3. Cancellation

Free and immediate while `PENDING`, through the account area or by contacting
support.

Once `PICKING` has begun, the order cannot be cancelled. The customer's options
are to refuse delivery, or accept and return under POL-RET-001. Refusing
delivery is treated as a change-of-mind return, so the return shipping rules in
POL-RET-001 section 5 apply by territory.

Pebble may cancel an order before dispatch where:

- payment authorisation fails on re-attempt
- fraud screening declines the order, subject to human review on request
- the item is out of stock and cannot be supplied within 30 days
- the listed price was obviously incorrect, per POL-PAY-005 section 8
- the delivery address is in a territory Pebble does not serve

## 4. Pre-orders and backorders

Pre-order items show an estimated dispatch window rather than a date. The
window may move, and the customer is emailed whenever it does.

- Pre-orders can be cancelled free of charge at any time before dispatch,
  including after the window has moved.
- Payment is authorised, not captured, until dispatch. See POL-PAY-005
  section 2.
- Where a pre-order and an in-stock item are ordered together, the whole order
  ships when the pre-order is ready. Customers who want the in-stock item
  sooner should order separately.
- If a pre-order slips more than 30 days beyond the original window, Pebble
  cancels and refunds automatically unless the customer asks to continue
  waiting.

## 5. Partial shipments

Pebble does not split orders by default. An order ships complete.

Splitting is done only when:

- a lithium item must travel by surface freight while the rest can fly, per
  POL-SHP-003 section 5
- one line is delayed beyond 14 days and the customer asks for the rest
- an item is damaged in the warehouse during picking

Where an order is split, no additional shipping is charged, and each parcel
receives its own tracking reference under the same `PB-nnnn` order.

## 6. Accounts

Guest checkout is available and does not create an account. A guest order can
be claimed into an account later using the order reference and the email
address it was placed with.

An account is required to:

- register a device for warranty
- purchase or hold PebbleCare+
- access digital licences and software keys
- use trade-in
- hold store credit

Account closure is self-service and takes effect immediately, subject to the
retention rules in POL-PRV-007 section 2. An account with an open order, an
open repair, or unspent store credit cannot be closed until those conclude;
support will explain which of the three is blocking.

Unspent store credit is forfeited on closure and is not refunded to a card.
Customers should be told this before closure proceeds.

## 7. Communication

| Email | Sent when |
| --- | --- |
| Order confirmation | Within 5 minutes of checkout |
| Dispatch notification with tracking | Within 24 hours of dispatch |
| Delivery confirmation | On carrier scan |
| Return received | On arrival at the returns centre |
| Refund processed | When Pebble releases the money, not when it lands |
| Pre-order window change | Whenever the window moves |

Transactional emails cannot be unsubscribed from while an order is active.
Marketing emails are separate and always unsubscribable, per POL-PRV-007
section 3.

## 8. What Pebble will never ask for

Pebble does not send links asking a customer to re-enter payment details to
"release" a parcel. Carriers acting for Pebble do not charge customers directly
for EU deliveries, per POL-SHP-003 section 3. Any message of that kind is
fraudulent and should be forwarded to `security@pebble.example`.
