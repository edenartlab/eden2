#uvicorn eve.api:web_app --host 0.0.0.0 --port 8000 --reload

import os
import json
import time
import subprocess
import requests

import eve
#from dotenv import load_dotenv
#load_dotenv(os.path.expanduser("~/.eve"))


EDEN_ADMIN_KEY = os.getenv("EDEN_ADMIN_KEY")
headers = {
    # "X-Api-Key": api_key,
    "Authorization": f"Bearer {EDEN_ADMIN_KEY}",
    "Content-Type": "application/json",
}

def run_chat(server_url):
    request = {
        "user_id": "65284b18f8bbb9bff13ebe65",
        "agent_id": "67069a27fa89a12910650755",
        "user_message": {
            "content": "make a picture of the best year ever",
        }
    }
    response = requests.post(server_url+"/chat", json=request, headers=headers)
    print("Status Code:", response.status_code)
    print(json.dumps(response.json(), indent=2))

def run_create(server_url):
    request = {
        "user_id": "65284b18f8bbb9bff13ebe65",
        "tool": "flux_dev",
        "args": {
            "prompt": "a picture of a fancy dog",
        }
    }
    response = requests.post(server_url+"/create", json=request, headers=headers)
    print(response)
    print("Status Code:", response.status_code)
    print(json.dumps(response.json(), indent=2))

def test_client():    
    run_server = True
    try:
        if run_server:
            server = subprocess.Popen(
                ["uvicorn", "eve.api:web_app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(2)
            server_url = "http://localhost:8000"
        else:
            server_url = "https://edenartlab--tools-new-dev-fastapi-app.modal.run"

        # Run the tests
        print("server_url", server_url)
        print("\nRunning chat test...")
        run_chat(server_url)
        
        print("\nRunning create test...")
        run_create(server_url)

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'server' in locals():
            server.terminate()
            server.wait()


if __name__ == "__main__":
    test_client()

