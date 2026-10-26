"""Safe error categories, without provider bodies or credentials."""


class ProviderError(ValueError):
    """Request failed without a usable diagnostic response."""


class ContractError(ValueError):
    """A response failed the output contract; counted as diagnostic risk."""


class ModelNoAnswer(ContractError):
    """No completed diagnosis; kept separate from an invalid diagnosis."""

    def __init__(self, reason):
        if reason not in ("refusal", "truncated", "filtered", "incomplete"):
            raise ValueError("Invalid no-answer reason")
        self.reason = reason
        super().__init__("No completed model diagnosis: " + reason)
