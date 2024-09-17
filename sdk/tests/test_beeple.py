from eden import EdenClient

eden_client = EdenClient()

args = {   
    "prompt": "Donald Trump bleeding from his ears",
    "seed": 42
}

response = eden_client.create(
    workflow="beeple_ai",
    args=args
)

print(response)
