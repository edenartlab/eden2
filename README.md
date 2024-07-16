# ComfyUI

Test a single workflow

    python comfyui.py test --workflows NAME_OF_WORKFLOW

Test multiple workflows

    python comfyui.py test --workflows NAME_OF_WORKFLOW1,NAME_OF_WORKFLOW2,...

Test all workflows

    python comfyui.py test

Push all workflows to staging:

    python comfyui.py deploy

Push all workflows to production:

    python comfyui.py deploy --production

Once workflows are pushed (to either stage or production), you can test the deployments using:

    python tests/test_comfyui.py --workflows NAME_OF_WORKFLOW1,NAME_OF_WORKFLOW2,...

Or test them all

    python tests/test_comfyui.py

To save all results to a local folder, include `--save` flag. To test production endpoints, use `--production`.


# Tools API

Test server

    modal serve api.py

Deploy api to stage.

    modal deploy api.py

Deploy api to production.

    ENV=PROD modal deploy api.py


# Interactive mode for threads

To interact with an agent, run

    python thread.py

To interact via client:

    eden chat