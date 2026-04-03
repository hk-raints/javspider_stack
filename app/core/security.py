from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key_header: str = Security(API_KEY_HEADER)):
    if not settings.API_KEY:
        return None
    
    if api_key_header == settings.API_KEY:
        return api_key_header
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate credentials",
    )
