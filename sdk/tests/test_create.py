from eden.client import EdenClient

client = EdenClient()

result = client.create("txt2img", {
    "prompt": "A mouse wearing a hat"
})

# result = client.create("xhibit/vton", {
#     "prompt": "A professioanl photo of <concept> as a fashion model",
#     "lora": "https://edenartlab-stage-data.s3.amazonaws.com/1190777f9d3337e2202fd0a27fc9e1c048a094d90e86f7d135bb21e09c9a2e15.tar",
#     "look_image": "https://static.toiimg.com/thumb/imgsize-23456,msid-67833030,width-600,resizemode-4/67833030.jpg"
# })


print(result)