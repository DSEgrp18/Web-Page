"""The API's routes, one module per area.

Each module has a ``register(app, deps)`` that adds its routes as closures over
the composition root, so a test swaps a store or an adapter through ``Deps``
without patching a module. Ownership is enforced in the store, and every route
uses ``owned`` (or, from Phase 2, ``readable``) before touching a document.
"""
