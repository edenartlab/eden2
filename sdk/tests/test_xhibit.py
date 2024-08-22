from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "A professioanl photo of <concept> as a fashion model",
    "lora": "66904ec042b902d8eb3b41e6",
    "look_image": "https://xhibitapp.s3.us-east-1.amazonaws.com/lookbook/1719403835835-853b29593f22b453cd63351e050bd823_exif.jpg",
    "face_image": "https://www.refinery29.com/images/11118508.jpg"
}
response = eden_client.create(
    workflow="xhibit/vton",
    args=args
)

print(response)
