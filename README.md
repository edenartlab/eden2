# ComfyUI

Test a single workflow

    ENV=name_of_environment modal run comfyui.py

If you just want to test only a subset of workflows, use:

    ENV=name_of_environment WORKFLOWS=workflow1,workflow2 modal run comfyui.py

Deploy a single workflow to stage.

    ENV=name_of_environment modal deploy comfyui.py

If you want to deploy a private environment, use `PRIVATE=1`

    ENV=name_of_private_env PRIVATE=1 modal deploy comfyui.py




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

