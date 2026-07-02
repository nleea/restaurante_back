"""Delivery module.

Models own-fleet delivery (no external apps): delivery routes/zones, which
employees (drivers) serve each route, dispatch runs grouping orders for a
driver, and the per-order delivery record with address, geo and explicit
status (pending → ... → delivered).
"""
