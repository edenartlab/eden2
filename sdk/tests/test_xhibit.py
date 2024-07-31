from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professioanl photo of <concept> as a fashion model",
    "lora": "66a96a3fc606643436ac2be8",
    "look_image": "https://xhibitapp.s3.us-east-1.amazonaws.com/lookbook/1719403835835-853b29593f22b453cd63351e050bd823_exif.jpg"
}
response = eden_client.create(
    workflow="xhibit/vton",
    args=args
)
print(response)
