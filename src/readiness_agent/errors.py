"""Safe error categories, without provider bodies or credentials."""


class ProviderError(ValueError):
    """Request failed; metadata is allowlisted, never copied from response bodies."""

    def __init__(self, message, *, http_status=None, retry_after_seconds=None,
                 transport_category=None):
        super().__init__(message)
        self.details = {}
        if type(http_status) is int and 100 <= http_status <= 599:
            self.details["http_status"] = http_status
        if type(retry_after_seconds) is int and 0 <= retry_after_seconds <= 3600:
            self.details["retry_after_seconds"] = retry_after_seconds
        if transport_category in ("timeout", "connection"):
            self.details["transport_category"] = transport_category



class ContractError(ValueError):
    """A response failed the output contract; counted as diagnostic risk."""


class ModelNoAnswer(ContractError):
    """No completed diagnosis; kept separate from an invalid diagnosis."""

    def __init__(self, reason):
        if reason not in ("refusal", "truncated", "filtered", "incomplete"):
            raise ValueError("Invalid no-answer reason")
        self.reason = reason
        super().__init__("No completed model diagnosis: " + reason)
