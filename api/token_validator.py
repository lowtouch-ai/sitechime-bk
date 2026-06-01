"""
Reverse proxy session token validation.

Validates the X-LTAI-EXT-API-TOKEN header before forwarding requests upstream.
Two strategies are supported, selected by PROXY_TOKEN_VALIDATION_STRATEGY:

  jwt_local       — Verify JWT signature + expiry locally using JWKS (no per-request network call).
  oidc_introspect — Call the OIDC token introspection endpoint (RFC 7662) per request.
  none            — Always pass (useful for local dev with validation enabled).
"""

import threading
import time
import logging

from django.conf import settings

security_logger = logging.getLogger('django.security')

# ---------------------------------------------------------------------------
# JWKS cache (used by JwtLocalValidator)
# ---------------------------------------------------------------------------
_jwks_cache: dict = {}
_jwks_lock = threading.Lock()
_JWKS_TTL_SECONDS = 900  # 15 minutes


def _fetch_jwks(uri: str) -> list:
    """Fetch JWKS keys from URI, returning the list of key dicts."""
    import requests as _requests
    resp = _requests.get(uri, timeout=5)
    resp.raise_for_status()
    return resp.json().get('keys', [])


def _get_jwks_keys(uri: str) -> list:
    """Return cached JWKS keys, refreshing if the TTL has elapsed."""
    now = time.monotonic()
    with _jwks_lock:
        entry = _jwks_cache.get(uri)
        if entry and now - entry['fetched_at'] < _JWKS_TTL_SECONDS:
            return entry['keys']
    # Fetch outside the lock to avoid blocking other threads during network I/O
    keys = _fetch_jwks(uri)
    with _jwks_lock:
        _jwks_cache[uri] = {'keys': keys, 'fetched_at': time.monotonic()}
    return keys


# ---------------------------------------------------------------------------
# Strategy: jwt_local
# ---------------------------------------------------------------------------

def _validate_jwt_local(token: str) -> tuple:
    import jwt as _jwt
    from jwt.algorithms import RSAAlgorithm, ECAlgorithm
    import json as _json

    jwks_uri = getattr(settings, 'OIDC_JWKS_URI', '')
    jwt_secret = getattr(settings, 'OIDC_JWT_SECRET', '')
    audience = getattr(settings, 'OIDC_JWT_AUDIENCE', None)
    issuer = getattr(settings, 'OIDC_JWT_ISSUER', None)

    decode_kwargs = {
        'algorithms': ['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512', 'HS256'],
        # Skip audience verification when OIDC_JWT_AUDIENCE is not configured —
        # PyJWT 2.x rejects tokens that contain an aud claim unless you explicitly
        # provide the expected audience or opt out of the check.
        'options': {'verify_exp': True, 'verify_aud': bool(audience)},
    }
    if audience:
        decode_kwargs['audience'] = audience
    if issuer:
        decode_kwargs['issuer'] = issuer

    if jwks_uri:
        # Decode header to find the key id
        try:
            header = _jwt.get_unverified_header(token)
        except _jwt.exceptions.DecodeError as exc:
            return False, f"malformed token header: {exc}"

        kid = header.get('kid')
        keys = _get_jwks_keys(jwks_uri)

        # Pick the matching key (or try all if no kid)
        candidates = [k for k in keys if not kid or k.get('kid') == kid]
        if not candidates:
            # Try refreshing the cache once in case the key was rotated
            with _jwks_lock:
                if jwks_uri in _jwks_cache:
                    del _jwks_cache[jwks_uri]
            keys = _get_jwks_keys(jwks_uri)
            candidates = [k for k in keys if not kid or k.get('kid') == kid]

        if not candidates:
            return False, "no matching JWKS key found"

        last_exc = None
        for jwk in candidates:
            try:
                alg = header.get('alg', 'RS256')
                if alg.startswith('RS'):
                    public_key = RSAAlgorithm.from_jwk(_json.dumps(jwk))
                elif alg.startswith('ES'):
                    public_key = ECAlgorithm.from_jwk(_json.dumps(jwk))
                else:
                    return False, f"unsupported algorithm: {alg}"
                _jwt.decode(token, public_key, algorithms=[alg], **{k: v for k, v in decode_kwargs.items() if k != 'algorithms'})
                return True, None
            except _jwt.exceptions.ExpiredSignatureError:
                return False, "token expired"
            except _jwt.exceptions.InvalidAudienceError:
                return False, "invalid audience"
            except _jwt.exceptions.InvalidIssuerError:
                return False, "invalid issuer"
            except Exception as exc:
                last_exc = exc
        return False, f"signature verification failed: {last_exc}"

    elif jwt_secret:
        try:
            _jwt.decode(token, jwt_secret, algorithms=['HS256'], **{k: v for k, v in decode_kwargs.items() if k != 'algorithms'})
            return True, None
        except _jwt.exceptions.ExpiredSignatureError:
            return False, "token expired"
        except Exception as exc:
            return False, str(exc)

    return False, "no OIDC_JWKS_URI or OIDC_JWT_SECRET configured"


# ---------------------------------------------------------------------------
# Strategy: oidc_introspect
# ---------------------------------------------------------------------------

def _validate_oidc_introspect(token: str) -> tuple:
    import requests as _requests

    endpoint = getattr(settings, 'OIDC_INTROSPECTION_ENDPOINT', '')
    client_id = getattr(settings, 'OIDC_CLIENT_ID', '')
    client_secret = getattr(settings, 'OIDC_CLIENT_SECRET', '')

    if not endpoint:
        return False, "OIDC_INTROSPECTION_ENDPOINT not configured"

    resp = _requests.post(
        endpoint,
        data={'token': token, 'token_type_hint': 'access_token'},
        auth=(client_id, client_secret) if client_id else None,
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('active') is True:
        return True, None
    return False, "token inactive or revoked"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_ext_api_token(token: str) -> tuple:
    """
    Validate the session token extracted from X-LTAI-EXT-API-TOKEN.

    Returns (True, None) on success, (False, reason_string) on failure.
    Never raises — exceptions are caught and handled per PROXY_TOKEN_VALIDATION_FAILURE_MODE.
    """
    strategy = getattr(settings, 'PROXY_TOKEN_VALIDATION_STRATEGY', 'jwt_local')
    failure_mode = getattr(settings, 'PROXY_TOKEN_VALIDATION_FAILURE_MODE', 'closed')

    if strategy == 'none':
        return True, None

    try:
        if strategy == 'jwt_local':
            return _validate_jwt_local(token)
        elif strategy == 'oidc_introspect':
            return _validate_oidc_introspect(token)
        else:
            security_logger.warning(f"Unknown PROXY_TOKEN_VALIDATION_STRATEGY: {strategy}")
            return False, f"unknown strategy: {strategy}"
    except Exception as exc:
        security_logger.error(f"Token validator raised an unexpected error: {exc}")
        if failure_mode == 'open':
            return True, None
        return False, "validator internal error"
