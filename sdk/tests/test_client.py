from eden.client import EdenClient

def test_run_workflow():
    from eden import EdenClient
    client = EdenClient()

    
    endpoint = "txt2img"
    config = {"prompt": "Hello World"}

    config = {
        "image": "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg",
        "video": "https://edenartlab-stage-data.s3.amazonaws.com/b09ed23211a88017430bd687b1989dcd41f18222343fcd8f133f7cda489100b0.mp4"
    }

    result = client.run(endpoint, config)
