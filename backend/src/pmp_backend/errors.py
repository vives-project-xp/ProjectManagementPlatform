"""Refusals raised by the services; app.py turns them into HTTP errors.

Every message is fit to show to the User. A plain `Refused` is a validation
problem (422); `NotFound` becomes 404, `Forbidden` 403 and `Conflict` 409. A
refusal a client must react to in a specific way (not just show) carries a `code`.
"""


class Refused(Exception):
    code: str | None = None


class NotFound(Refused):
    pass


class Forbidden(Refused):
    pass


class Conflict(Refused):
    pass
