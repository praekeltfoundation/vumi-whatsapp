import hmac
from base64 import b64encode
from functools import wraps
from hashlib import sha256
from typing import Callable

from sanic.exceptions import Forbidden, Unauthorized
from sanic.request import Request


def validate_hmac(header: str, secret: Callable):
    """
    Validates that the HMAC signature in `header` is a valid signature for the request
    body
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(request: Request, *args, **kwargs):
            s = secret()
            if s is None:
                # If no secret is configured, then don't validate
                return f(request, *args, **kwargs)
            if header not in request.headers or not request.headers[header]:
                raise Unauthorized(f"{header} not found in request headers")
            signature = request.headers[header]
            h = hmac.new(s.encode(), request.body, sha256)
            if not hmac.compare_digest(b64encode(h.digest()).decode(), signature):
                raise Forbidden("HMAC signature does not match")
            return f(request, *args, **kwargs)

        return decorated_function

    return decorator
