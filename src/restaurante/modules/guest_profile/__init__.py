"""Guest profile module: anonymous, cookie-identified customer contact data.

A parallel, account-free identity for storefront customers who order without
logging in. Persisted per tenant and keyed only by an opaque UUID token carried
in a dedicated ``guest_token`` cookie (never any personal data). Coexists with
the real-user JWT auth, which uses the ``Authorization`` header, not cookies.
"""
