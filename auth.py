import os
import jwt
from bson import ObjectId
from mongo import users, api_keys
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi import WebSocket, HTTPException, Depends, status

CLERK_PEM_PUBLIC_KEY = os.getenv("CLERK_PEM_PUBLIC_KEY")

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(api_key: str) -> dict:
    api_key = api_keys.find_one({"apiKey": api_key})
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    user = users.find_one({"_id": ObjectId(api_key["user"])})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def verify_bearer_token(token: str) -> dict:
    try:
        token = token.credentials
        decoded_token = jwt.decode(token, CLERK_PEM_PUBLIC_KEY, algorithms=["RS256"])
        user_id = decoded_token.get("sub")
        user = users.find_one({"userId": user_id})
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired Token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def authenticate(
    api_key: str = Depends(api_key_header),
    token: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if not api_key and not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No authentication credentials provided")
    return verify_api_key(api_key) if api_key else verify_bearer_token(token)


def authenticate_ws(websocket: WebSocket):
    api_key = websocket.headers.get("X-Api-Key")
    token = websocket.headers.get("Authorization")
    if token:
        token = HTTPAuthorizationCredentials(
            scheme="Bearer", 
            credentials=token.replace("Bearer ", "")
        )
    try:
        user = authenticate(api_key=api_key, token=token)
        return user
    except HTTPException as e:
        websocket.accept()
        websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        websocket.send_json({"error": e.detail})
        raise e

