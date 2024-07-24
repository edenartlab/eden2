import os
import dotenv
import requests
dotenv.load_dotenv()
EDEN_ADMIN_KEY=os.getenv("EDEN_ADMIN_KEY")


def test_post_request():
    url = "https://edenartlab--tools-dev-fastapi-app-dev.modal.run/create" 
    headers = {
        "Authorization": f"Bearer {EDEN_ADMIN_KEY}", 
        "Content-Type": "application/json"
    }
    payload1 = {
        "workflow": "txt2img",
        "args": {
            "prompt": "a waterfall made of athletic shoes, nice"
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }
    payload_train = {
        "workflow": "lora_trainer",
        "args": {
            "name": "Marzipan",
            "lora_training_urls": [
                'https://dtut5r9j4w7j4.cloudfront.net/2277f9e74da21857b4e1314b9d257d5bcb028cc0607c91b9a751bafa930f9451.jpg', 
                'https://dtut5r9j4w7j4.cloudfront.net/40f03d9e817866de6ab4b731a0c28484f85fee9c18eb3f1ce8ccbbfc94d29bbb.jpg', 
                'https://dtut5r9j4w7j4.cloudfront.net/be7cb5ac43af3793948f8f0b23abaa4da3184471d61a840e0048ccb360de9bbb.jpg', 
                'https://dtut5r9j4w7j4.cloudfront.net/f2bdd033c5721716430b3cfbd02caba545628e41a737ac7072c88c883b9d1c84.jpg', 
                'https://dtut5r9j4w7j4.cloudfront.net/c375a9364dca56769a38fbb2dabeee7e8b70d55af20f72ad08ce85100b0d20df.jpg', 
                'https://dtut5r9j4w7j4.cloudfront.net/a1cc987ae15500b61fa872de5ad59990c4646b2652585e14a34b5181353ecbff.jpg'
            ],
            "sd_model_version": "sdxl",
            "concept_mode": "face",
            "max_train_steps": 150
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }

    payload5 = {
        "workflow": "clarity_upscaler",
        "args": {
            "image": "http://4.bp.blogspot.com/-gx1tuHXeaSA/Tc2ut4VVvJI/AAAAAAAAAVs/6ND6FL1avvY/s1600/ben-grasso.jpg"
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }

    payload5 = {
        "workflow": "audiocraft",
        "args": {
            "text_input": "A piano solo in a crowded bar, chatter, jazzy, smoky",
            "model_name": "facebook/musicgen-medium",
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }


    payloadvid = {
        "workflow": "txt2vid",
        "args": {
            "prompt": "A piano solo in a crowded bar, chatter, jazzy, smoky",
            "n_frames": 128
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }


    # payload = {
    #     "workflow": "txt2img",
    #     "args": {
    #         "prompt": "hello api"
    #     },
    #     "user": "65284b18f8bbb9bff13ebe65"
    # }

#payload_train

    response = requests.post(url, json=payload_train, headers=headers)
    print(response)
    print(response.status_code)
    print(response.json())
    assert response.status_code == 200  # Adjust based on your expected status code
    print(response.json())  # Print the response for debugging


def test_reel():
    url = "https://edenartlab--tools-dev-fastapi-app-dev.modal.run/create" 
    headers = {
        "Authorization": f"Bearer {EDEN_ADMIN_KEY}", 
        "Content-Type": "application/json"
    }
    payload = {
        "workflow": "reel",
        "args": {
            "prompt": "a piano recital",
            "music": True,
            "music_prompt": "a piano solo in a crowded bar, chatter, jazzy, smoky"
        },
        "user": "65284b18f8bbb9bff13ebe65"
    }

    response = requests.post(url, json=payload, headers=headers)
    print(response)
    print(response.status_code)
    assert response.status_code == 200


def test_cancel_request():
    url = "https://edenartlab--tools-dev-fastapi-app-dev.modal.run/cancel"
    payloadc = {
        "taskId": "6699a146c231abbd54ef59bb"
    }
    headers = {
        "Authorization": f"Bearer {EDEN_ADMIN_KEY}", 
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payloadc, headers=headers)
    print(response)
    print(response.status_code)
    print(response.json())
    assert response.status_code == 200  # Adjust based on your expected status code
    print(response.json())  # Print the response for debugging


# test_cancel_request()
test_post_request()
# test_reel()