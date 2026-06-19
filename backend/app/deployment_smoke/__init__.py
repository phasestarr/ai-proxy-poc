"""
Deployment-only smoke checks.

This package must not use public API auth/session/chat routes. The smoke gate
is allowed to touch external providers, but it must not create product users,
sessions, histories, messages, stored files, or operator-event rows.
"""

