"""
Purpose:
- Define shared backend exception types and error translation rules.

Planned responsibilities:
- Provide custom exception classes for service and provider layers
- Normalize internal failures into predictable API-facing errors

Notes:
- Keep exception naming explicit.
- Avoid leaking raw provider or infrastructure errors directly to clients.
"""
