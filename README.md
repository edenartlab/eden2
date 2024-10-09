# ComfyUI

Test a single workspace

    WORKSPACE=name_of_workspace modal run comfyui.py

If you just want to test only a subset of workflows in a workspace, use:

    WORKSPACE=name_of_workspace WORKFLOWS=workflow1,workflow2 modal run comfyui.py

Deploy a single workspace to stage.

    WORKSPACE=name_of_workspace modal deploy comfyui.py

### Additional FLAGS:
If you want to run all the test*.json tests, use `TEST_ALL=1`
    WORKSPACE=img_tools WORKFLOWS=upscaler TEST_ALL=1 modal run comfyui.py

If you want to deploy a private workspace, use `PRIVATE=1`
    WORKSPACE=name_of_private_workspace PRIVATE=1 modal deploy comfyui.py


# Testing deployed tools

To test a tool directly, run:

    python test_tools.py --tools tool1 tool2

To test a tool through the tools API, run:

    python test_api.py --tools tool1 tool2

To test a tool from the SDK through the API, run:

    python test_sdk.py --tools tool1 tool2

All of these will test using the staging API, so make sure you are running the API (see next section). If you want to test production, include the `--production` flag. If you want to test all the tools, omit the `--tools` parameter.


# Update API

To update the API interface

    python config.py --env {STAGE|PROD}

### Optional Flags

To update only specific tools:

    python config.py --env STAGE --tools tool1 tool2 tool3

Available options:
- `--env`: STAGE or PROD (default is STAGE)
- `--tools`: Space-separated list of tool names to update (otherwise all found tools will be updated)


# Tools API

Test server

    modal serve api.py

Deploy api to stage.

    modal deploy api.py

Deploy api to production.

    ENV=PROD modal deploy api.py


# Interactive mode for threads (WIP)

To interact with an agent, run

    python thread.py

