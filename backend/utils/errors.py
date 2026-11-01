from __future__ import annotations


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class ValidationError(ApiError):
    def __init__(self, message: str, details=None):
        super().__init__("validation_error", message, 422, details)


class NotFoundError(ApiError):
    def __init__(self, message: str = "The requested record was not found."):
        super().__init__("not_found", message, 404)


class ConflictError(ApiError):
    def __init__(self, message: str, details=None):
        super().__init__("conflict", message, 409, details)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__("forbidden", message, 403)
