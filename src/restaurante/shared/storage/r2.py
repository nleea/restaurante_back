"""Cloudflare R2 uploads via AWS SigV4 presigned PUT URLs — stdlib only, no boto3.

R2 is S3-compatible: region ``auto``, service ``s3``, endpoint
``https://<account_id>.r2.cloudflarestorage.com``. We presign a PUT so the browser uploads
the file straight to the bucket (the API never proxies the bytes and R2 credentials never
leave the server). Only the ``host`` header is signed and the payload is ``UNSIGNED-PAYLOAD``,
so the client may send any Content-Type.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from urllib.parse import quote, urlparse

_ALGORITHM = "AWS4-HMAC-SHA256"
_REGION = "auto"
_SERVICE = "s3"

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

def _signing_key(secret: str, datestamp: str) -> bytes:
    k_date = _hmac(f"AWS4{secret}".encode(), datestamp)
    k_region = _hmac(k_date, _REGION)
    k_service = _hmac(k_region, _SERVICE)
    return _hmac(k_service, "aws4_request")


class R2Storage:
    """Presigns PUT uploads and builds public URLs for a configured R2 bucket."""

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str,
        endpoint_url: str = "",
    ) -> None:
        self._account_id = account_id
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._public_base_url = public_base_url
        self._endpoint_url = endpoint_url.rstrip("/")

    def _scheme_host(self) -> tuple[str, str]:
        """(scheme, host) to sign against and to build the upload URL — always consistent.

        Uses the explicit endpoint when set (e.g. a jurisdiction host), else the standard
        account endpoint.
        """
        if self._endpoint_url:
            parsed = urlparse(self._endpoint_url)
            return parsed.scheme or "https", parsed.netloc
        return "https", f"{self._account_id}.r2.cloudflarestorage.com"

    @property
    def is_configured(self) -> bool:
        return all(
            [
                self._account_id,
                self._access_key_id,
                self._secret_access_key,
                self._bucket,
                self._public_base_url,
            ]
        )

    def public_url(self, key: str) -> str:
        return f"{self._public_base_url.rstrip('/')}/{key}"

    def presign_put(
        self, key: str, *, now: datetime, expires_seconds: int = 300
    ) -> str:
        """A SigV4 presigned PUT URL for ``key``, valid ``expires_seconds`` from ``now`` (UTC)."""
        scheme, host = self._scheme_host()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        canonical_uri = "/" + quote(f"{self._bucket}/{key}", safe="/")
        credential_scope = f"{datestamp}/{_REGION}/{_SERVICE}/aws4_request"

        params = {
            "X-Amz-Algorithm": _ALGORITHM,
            "X-Amz-Credential": f"{self._access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_seconds),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_querystring = "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}"
            for k, v in sorted(params.items())
        )
        canonical_request = "\n".join(
            [
                "PUT",
                canonical_uri,
                canonical_querystring,
                f"host:{host}\n",
                "host",
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                _ALGORITHM,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self._secret_access_key, datestamp),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        return (
            f"{scheme}://{host}{canonical_uri}"
            f"?{canonical_querystring}&X-Amz-Signature={signature}"
        )
