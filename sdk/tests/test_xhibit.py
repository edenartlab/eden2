from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professioanl photo of <concept> as a fashion model",
    "lora": "https://edenartlab-stage-data.s3.amazonaws.com/5a4679d889a7d0c8506a3e6de7ee4e1d37e791c9d682b9f52c8bcdda4ce3125b.tar",
    "look_image": "https://xhibitapp.s3.us-east-1.amazonaws.com/lookbook/1719403835835-853b29593f22b453cd63351e050bd823_exif.jpg"
}
response = eden_client.create(
    workflow="xhibit/vton",
    args=args
)
print(response)
