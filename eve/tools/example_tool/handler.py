from ...eden_utils import download_file

async def handler(args: dict, env: str):   
    # download this file
    path = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg"
    image_path = download_file(path, "myimg1.jpg")
    
    # raise Exception("This is an error 55")

    result = {
        "output": image_path,
        "intermediate_outputs": {
            "key1": "value1",
            "key2": "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg",
            "key3": "args",
        }
    }
    return result