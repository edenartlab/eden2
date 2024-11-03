from eden_utils import download_file

async def tool1(args: dict, env: str):   
    # download this file
    path = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg"
    image_path = download_file(path, "myimg1.jpg")
    
    result = {
        "output": image_path
    }
    return result