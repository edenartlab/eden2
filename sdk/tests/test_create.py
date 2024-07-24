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
    "prompt": "<concept> in a forest",
    "lora": "66965fe5886103b0e9066945",
    "lora_strength": 0.6,
    "width": 1920,
    "height": 1080,
})
print(result)