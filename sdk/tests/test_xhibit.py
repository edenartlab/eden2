from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professional photo of <concept> as a fashion model looking fresh, beautiful, youthful, easeful, bright.",
    "lora": "66df0f78634f1d2968c89f98",
    "look_image": "https://storage.googleapis.com/public-assets-xander/Random/remove/xhibit/test2.jpeg",
    "face_image": "https://storage.googleapis.com/public-assets-xander/Random/remove/xhibit/face.jpeg",
    "resolution": 1152
}

response = eden_client.create(
    workflow="xhibit_vton",
    args=args
)

print(response)
