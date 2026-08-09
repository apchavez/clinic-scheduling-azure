"""Domain-level exceptions shared across use cases and entities."""


class IllegalStateError(RuntimeError):
    """Raised when a state-transition guard is violated (mirrors Java's IllegalStateException).

    Handlers map this to 404 if the message starts with "Appointment not found", else 409.
    """


class ForbiddenError(RuntimeError):
    """Raised when a requesting user is not allowed to act on/view a given appointment."""
