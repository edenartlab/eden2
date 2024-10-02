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

    python test_tools.py --tools tool1,tool2,etc

To test a tool through the tools API, run:

    python test_api.py --tools tool1,tool2,etc

To test a tool from the SDK through the API, run:

    python test_sdk.py --tools tool1,tool2,etc

All of these will test using the staging API, so make sure you are running the API (see next section). If you want to test production, include the `--production` flag. If you want to test all the tools, omit the `--tools` parameter.


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



# Generic flow for adding a new endpoint (`background_removal` in this example) on Eden:
1. Build the workflow on ComfyUI Localhost
2. Create api.yaml for mapping parameters to comfyui nodes, add documentation and agent tips. Also create test.json file(s)
3. Export workflow_api.json and your local snapshot.json
4. Use tools in https://github.com/edenartlab/workflows/tree/main/_utils to auto-generate downloads.json and snapshot.json for this workflow
5. Merge workflow downloads and snapshot into workspace downloads and snapshot (using `workflows/_utils/generate_environment.py`)
6. Run modal test, eg: `WORKSPACE=txt2img WORKFLOWS=background_removal modal run comfyui.py`
7. When base test looks good, optionally run all tests to validate multiple pathways and auto-download all dependencies into the image: `WORKSPACE=txt2img WORKFLOWS=background_removal TEST_ALL=1 modal run comfyui.py`
8. Now, deploy the full workspace (to staging): `WORKSPACE=txt2img modal deploy comfyui.py`
9. Test the new tool through the (staging) API: `python test_api.py --tools background_removal`
10. Deploy updated workspace to production: `ENV=PROD WORKSPACE=txt2img modal deploy comfyui.py`
11. Test deployed tool through production api: `python test_api.py --tools background_removal --production`

