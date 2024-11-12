# SDK reference

Install the SDK:

    pip install --upgrade git+https://github.com/edenartlab/eden2/#subdirectory=sdk

Get an API key from the app, and then run:

    eden login

This will put your token in a file called `.eden` in your home directory. Alternatively you can set the environmental variable `EDEN_API_KEY`.

# Usage


```
from eden import EdenClient
eden_client = EdenClient()

# txt2img
response = eden_client.create(
    workflow="txt2img", 
    args={
        "prompt": "An astronaut riding a horse",
        "width": 1024, 
        "height": 1440
    }
)
```

