class WorkerError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class SourceExpired(WorkerError):
    def __init__(self):
        super().__init__("SOURCE_EXPIRED", "Source is no longer available.", False)


class LeaseLost(Exception):
    """We no longer own the job (expired, reclaimed or cancelled): stop, clean up, report nothing."""
