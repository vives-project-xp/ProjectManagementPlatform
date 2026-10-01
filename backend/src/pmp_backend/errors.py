"""Refusals raised by the services; app.py turns them into HTTP errors.

Every message is fit to show to the User. A plain `Refused` is a validation
problem (422); `NotFound` becomes 404 and `Conflict` 409.
"""


class Refused(Exception):
    pass


class NotFound(Refused):
    pass


class Conflict(Refused):
    pass
