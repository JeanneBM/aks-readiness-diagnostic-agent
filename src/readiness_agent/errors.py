"""Safe error categories, without provider bodies or credentials."""


class ProviderError(ValueError):
    """Request failed without a usable diagnostic response."""


class ContractError(ValueError):
    """A response failed the output contract; counted as diagnostic risk."""
