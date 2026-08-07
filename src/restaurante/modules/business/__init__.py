"""Business module: the negocio's identity and structured operating hours.

The consolidated source of truth for who the business is (name, photo, contact) and
per-branch operating hours. Hours *inform* — they drive the storefront's "abrimos a
las X" copy and future auto-behaviours — but do NOT gate orders: the open cash session
is the operational gate (see the cash-session-operating-shift change).
"""
