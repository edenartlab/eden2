from eden.client import EdenClient

client = EdenClient()

result = client.create("txt2img", {
    "prompt": "Hello Eden"
})

print(result)