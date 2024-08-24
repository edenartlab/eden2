import os
import jwt
from bson import ObjectId
from mongo import mongo_client
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi import WebSocket, HTTPException, Depends, status

CLERK_PEM_PUBLIC_KEY = os.getenv("CLERK_PEM_PUBLIC_KEY")
ADMIN_KEY = os.getenv("ADMIN_KEY")

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

env = os.getenv("ENV")
db_name = "eden-prod" if env == "PROD" else "eden-stg"
api_keys = mongo_client[db_name]["apikeys"]
users = mongo_client[db_name]["users"]

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, 
                            detail="No authentication credentials provided")
    return verify_api_key(api_key) if api_key else verify_bearer_token(token)


async def authenticate_ws(websocket: WebSocket):
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
        await websocket.accept()
        await websocket.send_json({"error": e.detail})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise e


def authenticate_admin(
    token: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    print("token", token)
    print("token.credentials", token.credentials)
    print("ADMIN_KEY", ADMIN_KEY)
    print("GO!")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, 
                            detail="No authentication credentials provided")
    if token.credentials != ADMIN_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


# def authenticate_socketio(environ):
#     api_key = environ.get('HTTP_X_API_KEY')
#     token = environ.get('HTTP_AUTHORIZATION')
#     if token:
#         token = HTTPAuthorizationCredentials(
#             scheme="Bearer", 
#             credentials=token.replace("Bearer ", "").strip()
#         )
#     user = authenticate(api_key=api_key, token=token)
#     return user
