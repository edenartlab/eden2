from eden import EdenClient

eden_client = EdenClient()

args = {   
    # "prompt": "A professioanl photo of <concept> as a fashion model",
    # "lora": "https://edenartlab-stage-data.s3.amazonaws.com/1190777f9d3337e2202fd0a27fc9e1c048a094d90e86f7d135bb21e09c9a2e15.tar",
    # "look_image": "https://dtut5r9j4w7j4.cloudfront.net/a51c98b5b18472d2e71f6a421094e676b0f3ae0d7a523af6397818f6b2316210.png"
    "prompt": "A professioanl photo of Vanessa as a fashion model",
    "lora": "https://edenartlab-stage-data.s3.amazonaws.com/5a4679d889a7d0c8506a3e6de7ee4e1d37e791c9d682b9f52c8bcdda4ce3125b.tar",
    "look_image": "https://xhibitapp.s3.us-east-1.amazonaws.com/lookbook/1719403835835-853b29593f22b453cd63351e050bd823_exif.jpg"

}
# response = eden_client.create(
#     workflow="xhibit/vton",
#     args=args
# )
# print(response)




args = {   
    "input_image": "https://www.refinery29.com/images/11118508.jpg",
    "prompt": "a professional photo of Vanessa as a fashion model",
    "lora": "https://edenartlab-stage-data.s3.amazonaws.com/1190777f9d3337e2202fd0a27fc9e1c048a094d90e86f7d135bb21e09c9a2e15.tar"
}
response = eden_client.create(
    workflow="xhibit/remix",
    args=args
)
print(response)
