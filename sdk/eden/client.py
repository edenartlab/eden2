import asyncio
import websockets
import json
from pydantic import BaseModel
from typing import Dict, Any, Optional


DEFAULT_URL = "wss://edenartlab--eden-server-fastapi-app-dev.modal.run"


class EdenClient:
    def __init__(self, url=DEFAULT_URL):
        self.url = url
        self.api_key = None

    async def run(self, workflow, config):
        headers = {"Authorization": "Bearer eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18yVXluSWYzVXVRNDdBNEdyZm1ITFdjME1rOWUiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwczovL2FwcC5lZGVuLmFydCIsImV4cCI6MTcxNTUwMzQ1OSwiaWF0IjoxNzE1NTAzMzk5LCJpc3MiOiJodHRwczovL2NsZXJrLmVkZW4uYXJ0IiwibmJmIjoxNzE1NTAzMzg5LCJzaWQiOiJzZXNzXzJnS1RzQUVxbkx5SFJ1R2ptNDZDM1RYR21uVyIsInN1YiI6InVzZXJfMldkOUplY1BEcXJ5WTJPVFhaM0FCV1BWZEFlIn0.Y2wFwUaHmmlY8ynf7-Y1nJoAvQEocfE9mxohIMvRrL8zYhe-7SxyPW7aG7ApfeSOpwk0DUAVANiWn_5ZbLiKwHrdCtJ87PqY_NuK3-YlQdmYwgaEiu1xprEre2iy_vc2oAjyB6p2XnPPbjb7V_eNVJLN0L3rI5u1rlC41SI884PR_5CjG29LAnR6jShpDnSYCvK4rNmH0KM6aOekrM_OYQ-M23Xy18DnBJRUuiObBFPca7bHZyOZqf7elxR2om9QbFCqBLR5GdS8IX3dXkk9Oi9jxTp4pIwpatjKA8tARuFL9JNopQoDh6JbAJ81AfdIZ_WT8PgSnJyHfzmpJSst_A"}
        #headers = {"X-Api-Key": self.api_key}
        
        class WorkflowRequest(BaseModel):
            workflow: str
            config: Dict[str, Any]
            client_id: Optional[str] = None

        job_request = WorkflowRequest(
            workflow=workflow,
            config=config
        )

        try:
            async with websockets.connect(f"{self.url}/ws/tasks/run", extra_headers=headers) as websocket:
                await websocket.send(json.dumps(job_request.dict()))
                result = await websocket.recv()
                job_result = json.loads(result)
                print(f"Received result: {job_result}")
                return job_result
                #print(f"Status: {job_result['status']}")
                #print(f"Result: {job_result['result']}")
                #print(f"Duration: {job_result['duration']} seconds")
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"Failed to connect with status code: {e.status_code}")
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"Connection was closed unexpectedly: {e}")
        except asyncio.TimeoutError:
            print("Connection attempt timed out")
        except websockets.exceptions.WebSocketException as e:
            print(f"Websocket error: {e}")

    