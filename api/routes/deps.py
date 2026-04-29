from fastapi import Header, HTTPException
import os

VALID_API_KEY = os.environ.get("PIZZASTACK_API_KEY", None)


async def verify_api_key(x_api_key: str = Header(...)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if VALID_API_KEY and x_api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_session_id(x_session_id: str = Header(...)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Missing session ID")
    return x_session_id
