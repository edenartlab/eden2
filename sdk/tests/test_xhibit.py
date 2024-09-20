from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professional photo of <concept> as a fashion model looking fresh, beautiful, youthful, easeful, bright.",
    "lora": "66904ec042b902d8eb3b41e6",
    "look_image": "https://storage.googleapis.com/public-assets-xander/Random/remove/xhibit/test2.jpeg",
    "face_image": "https://storage.googleapis.com/public-assets-xander/Random/remove/xhibit/face.jpeg",
    "resolution": 1152
}

response = eden_client.create(
    workflow="xhibit_vton",
    args=args
)

print(response)
