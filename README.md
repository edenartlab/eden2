# ComfyUI

Test a single workflow

    ENV=name_of_environment modal run comfyui2.py

Deploy a single workflow to stage.

    ENV=name_of_environment modal deploy comfyui2.py

Deploy a single workflow to prod (dangerous).

    ENV=name_of_environment APP=prod modal deploy comfyui2.py


## Todo

- test one workflow instead of all of them
- re-evaluate naming conventions




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