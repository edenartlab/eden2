import os
import dotenv
import requests
dotenv.load_dotenv()
EDEN_ADMIN_KEY=os.getenv("EDEN_ADMIN_KEY")


def test_post_request():
    url = "https://edenartlab--tasks2-fastapi-app-dev.modal.run/create" 
    headers = {
        "Authorization": f"Bearer {EDEN_ADMIN_KEY}", 
        "Content-Type": "application/json"
    }
    payload = {
        "workflow": "txt2img",
        "args": {
            "prompt": "hello api"
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }
    response = requests.post(url, json=payload, headers=headers)
    print(response)
    assert response.status_code == 200  # Adjust based on your expected status code
    print(response.json())  # Print the response for debugging


test_post_request()