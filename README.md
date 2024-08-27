# ComfyUI

Test a single workspace

    WORKSPACE=name_of_workspace modal run comfyui.py

If you just want to test only a subset of workflows in a workspace, use:

    WORKSPACE=name_of_workspace WORKFLOWS=workflow1,workflow2 modal run comfyui.py

Deploy a single workspace to stage.

    WORKSPACE=name_of_workspace modal deploy comfyui.py

If you want to deploy a private workspace, use `PRIVATE=1`

    WORKSPACE=name_of_private_workspace PRIVATE=1 modal deploy comfyui.py




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

