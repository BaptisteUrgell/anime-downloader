class DomainError(Exception):
    pass


class InvalidSourceUrl(DomainError):
    pass


class NoAdapterFound(DomainError):
    pass


class DiscoveryFailed(DomainError):
    pass


class JobNotFound(DomainError):
    pass


class SeasonNotFound(DomainError):
    pass


class NoFailedEpisodes(DomainError):
    pass


class JobCannotBeDismissed(DomainError):
    pass