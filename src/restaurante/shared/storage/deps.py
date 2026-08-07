from functools import lru_cache

from restaurante.shared.config import get_settings
from restaurante.shared.storage.r2 import R2Storage


@lru_cache
def build_object_storage():
    s = get_settings()
    
    if s.storage == "r2":
        return R2Storage(
            account_id=s.r2_account_id,
            access_key_id=s.r2_access_key_id,
            secret_access_key=s.r2_secret_access_key,
            bucket=s.r2_bucket,
            public_base_url=s.r2_public_base_url,
            endpoint_url=s.r2_endpoint_url,
        )