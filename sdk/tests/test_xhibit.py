from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professioanl photo of <concept> as a fashion model",
    "lora": "https://edenartlab-stage-data.s3.amazonaws.com/1190777f9d3337e2202fd0a27fc9e1c048a094d90e86f7d135bb21e09c9a2e15.tar",
    "look_image": "https://dtut5r9j4w7j4.cloudfront.net/a51c98b5b18472d2e71f6a421094e676b0f3ae0d7a523af6397818f6b2316210.png"
}
response = eden_client.create(
    workflow="xhbit/vton",
    args=args
)
print(response)
