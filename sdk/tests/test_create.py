from eden.client import EdenClient

client = EdenClient()

# result = client.create("txt2vid_lora", {
#     "prompt": "<concept> in a forest",
#     "lora": "66965fe5886103b0e9066945",
#     "lora_strength": 0.6,
#     "width": 1024,
#     "height": 768,
#     "n_frames": 128
# })

result = client.create("txt2img", {
    "prompt": "<concept> under a rainbow",
    "lora": "66c2bf435ec7b6d95deb7223",
    "lora_strength": 0.3,
    "width": 1280,
    "height": 768,
})
print(result)