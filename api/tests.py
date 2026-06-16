import json
import threading
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings


# ---------------------------------------------------------------------------
# Helpers — generate real RSA keys so tests exercise actual crypto
# ---------------------------------------------------------------------------

def _make_rsa_key_pair():
    """Return (private_key, public_key_jwk_dict) for test JWT signing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()
    jwk_str = RSAAlgorithm.to_jwk(public_key)
    jwk_dict = json.loads(jwk_str)
    jwk_dict['kid'] = 'test-key-1'
    return private_key, jwk_dict


def _sign_jwt(private_key, payload: dict, algorithm: str = 'RS256', kid: str = 'test-key-1') -> str:
    import jwt
    headers = {'kid': kid} if kid else {}
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


# ---------------------------------------------------------------------------
# jwt_local strategy tests
# ---------------------------------------------------------------------------

class JwtLocalValidatorTests(TestCase):

    def setUp(self):
        self.private_key, self.jwk_dict = _make_rsa_key_pair()

    def _mock_jwks(self):
        return patch('api.token_validator._fetch_jwks', return_value=[self.jwk_dict])

    def _valid_payload(self, offset: int = 3600) -> dict:
        return {'sub': 'user@example.com', 'exp': int(time.time()) + offset}

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_valid_rs256_token_passes(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        with self._mock_jwks():
            ok, reason = validate_ext_api_token(token)
        self.assertTrue(ok, reason)
        self.assertIsNone(reason)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_expired_token_rejected(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, {'sub': 'u', 'exp': int(time.time()) - 10})
        with self._mock_jwks():
            ok, reason = validate_ext_api_token(token)
        self.assertFalse(ok)
        self.assertIn('expired', reason)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_tampered_payload_rejected(self):
        import base64
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        header, _, sig = token.split('.')
        fake_payload = base64.urlsafe_b64encode(
            json.dumps({'sub': 'attacker', 'exp': int(time.time()) + 9999}).encode()
        ).rstrip(b'=').decode()
        tampered = f"{header}.{fake_payload}.{sig}"
        with self._mock_jwks():
            ok, _ = validate_ext_api_token(tampered)
        self.assertFalse(ok)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_alg_none_rejected(self):
        import base64
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        header = base64.urlsafe_b64encode(
            json.dumps({'alg': 'none', 'typ': 'JWT'}).encode()
        ).rstrip(b'=').decode()
        payload = base64.urlsafe_b64encode(
            json.dumps(self._valid_payload()).encode()
        ).rstrip(b'=').decode()
        token = f"{header}.{payload}."
        with self._mock_jwks():
            ok, reason = validate_ext_api_token(token)
        self.assertFalse(ok)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_hs256_rejected_on_jwks_path(self):
        """
        Critical security invariant: HS256 must be rejected when validating against JWKS.
        Allowing HS256 enables algorithm-confusion attacks where an attacker can sign
        a token using the RSA public key as the HMAC secret.
        """
        import jwt
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = jwt.encode(self._valid_payload(), 'any-secret', algorithm='HS256',
                           headers={'kid': 'test-key-1'})
        with self._mock_jwks():
            ok, reason = validate_ext_api_token(token)
        self.assertFalse(ok)
        self.assertIn('not allowed', reason)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        OIDC_JWKS_CACHE_TTL_SECONDS=1,
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_jwks_cache_refreshes_after_ttl(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        call_count = {'n': 0}

        def counting_fetch(uri):
            call_count['n'] += 1
            return [self.jwk_dict]

        with patch('api.token_validator._fetch_jwks', side_effect=counting_fetch):
            validate_ext_api_token(token)
            time.sleep(1.1)
            validate_ext_api_token(token)

        self.assertGreaterEqual(call_count['n'], 2, "JWKS should be re-fetched after TTL expires")

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
    )
    def test_concurrent_cache_access_is_thread_safe(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        errors = []

        def worker():
            try:
                with patch('api.token_validator._fetch_jwks', return_value=[self.jwk_dict]):
                    ok, reason = validate_ext_api_token(token)
                    if not ok:
                        errors.append(f'validation failed: {reason}')
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread-safety errors: {errors}")

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
        PROXY_TOKEN_VALIDATION_FAILURE_MODE='closed',
    )
    def test_failure_mode_closed_returns_false_on_network_error(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        with patch('api.token_validator._fetch_jwks', side_effect=Exception("network error")):
            ok, _ = validate_ext_api_token(token)
        self.assertFalse(ok)

    @override_settings(
        OIDC_JWKS_URI='https://provider/.well-known/jwks.json',
        PROXY_TOKEN_VALIDATION_STRATEGY='jwt_local',
        PROXY_TOKEN_VALIDATION_FAILURE_MODE='open',
    )
    def test_failure_mode_open_returns_true_on_network_error(self):
        from api.token_validator import validate_ext_api_token, _jwks_cache
        _jwks_cache.clear()
        token = _sign_jwt(self.private_key, self._valid_payload())
        with patch('api.token_validator._fetch_jwks', side_effect=Exception("network error")):
            ok, _ = validate_ext_api_token(token)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# none strategy tests
# ---------------------------------------------------------------------------

class NoneStrategyTests(TestCase):

    @override_settings(PROXY_TOKEN_VALIDATION_STRATEGY='none')
    def test_none_strategy_always_passes(self):
        from api.token_validator import validate_ext_api_token
        ok, reason = validate_ext_api_token('anything')
        self.assertTrue(ok)
        self.assertIsNone(reason)

    @override_settings(PROXY_TOKEN_VALIDATION_STRATEGY='none')
    def test_none_strategy_logs_warning(self):
        from api.token_validator import validate_ext_api_token
        with self.assertLogs('django.security', level='WARNING') as cm:
            validate_ext_api_token('anything')
        self.assertTrue(any('DISABLED' in line for line in cm.output))


# ---------------------------------------------------------------------------
# oidc_introspect strategy tests
# ---------------------------------------------------------------------------

class OidcIntrospectTests(TestCase):

    @override_settings(
        PROXY_TOKEN_VALIDATION_STRATEGY='oidc_introspect',
        OIDC_INTROSPECTION_ENDPOINT='https://provider/introspect',
        OIDC_CLIENT_ID='client',
        OIDC_CLIENT_SECRET='secret',
    )
    def test_inactive_token_rejected(self):
        from api.token_validator import _validate_oidc_introspect

        mock_resp = MagicMock()
        mock_resp.json.return_value = {'active': False}
        mock_resp.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_resp):
            ok, reason = _validate_oidc_introspect('some-token')
        self.assertFalse(ok)
        self.assertIn('inactive', reason)

    @override_settings(
        PROXY_TOKEN_VALIDATION_STRATEGY='oidc_introspect',
        OIDC_INTROSPECTION_ENDPOINT='https://provider/introspect',
    )
    def test_active_token_passes(self):
        from api.token_validator import _validate_oidc_introspect

        mock_resp = MagicMock()
        mock_resp.json.return_value = {'active': True}
        mock_resp.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_resp):
            ok, reason = _validate_oidc_introspect('good-token')
        self.assertTrue(ok)
        self.assertIsNone(reason)

    @override_settings(
        OIDC_INTROSPECTION_ENDPOINT='https://provider/introspect',
    )
    def test_slow_endpoint_logs_warning(self):
        from api.token_validator import _validate_oidc_introspect

        mock_resp = MagicMock()
        mock_resp.json.return_value = {'active': True}
        mock_resp.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_resp):
            # Patch time.monotonic to simulate a 2.5-second response
            with patch('api.token_validator.time') as mock_time:
                mock_time.monotonic.side_effect = [0.0, 2.5]
                with self.assertLogs('django.security', level='WARNING') as cm:
                    _validate_oidc_introspect('token')
        self.assertTrue(any('2.5s' in line for line in cm.output))
