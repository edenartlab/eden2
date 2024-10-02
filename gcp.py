import os
import time
from google.cloud import aiplatform
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

# authenticate
credentials = service_account.Credentials.from_service_account_info({
    "type": os.environ["GCP_TYPE"],
    "project_id": os.environ["GCP_PROJECT_ID"],
    "private_key_id": os.environ["GCP_PRIVATE_KEY_ID"],
    "private_key": os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": os.environ["GCP_CLIENT_EMAIL"],
    "client_id": os.environ["GCP_CLIENT_ID"],
    "auth_uri": os.environ["GCP_AUTH_URI"],
    "token_uri": os.environ["GCP_TOKEN_URI"],
    "auth_provider_x509_cert_url": os.environ["GCP_AUTH_PROVIDER_X509_CERT_URL"],
    "client_x509_cert_url": os.environ["GCP_CLIENT_X509_CERT_URL"]
})

# initialize client
project_id = os.environ["GCP_PROJECT_ID"]
location = os.environ["GCP_LOCATION"]
staging_bucket = os.environ["GCP_STAGING_BUCKET"]

aiplatform.init(
    project=project_id, 
    location=location, 
    credentials=credentials, 
    staging_bucket=staging_bucket
)

GPUs = {
    "A100": aiplatform.gapic.AcceleratorType.NVIDIA_TESLA_A100,
    "T4": aiplatform.gapic.AcceleratorType.NVIDIA_TESLA_T4
}


async def submit_job(
    gcr_image_uri,
    machine_type,
    gpu,
    gpu_count,
    task_id, 
    env
):
    job_name = f"flux-{task_id}"
    job = aiplatform.CustomJob(
        display_name=job_name,
        worker_pool_specs=[
            {
                "machine_spec": {
                    "machine_type": machine_type,
                    "accelerator_type": GPUs[gpu],
                    "accelerator_count": gpu_count,
                },
                "replica_count": 1,
                "container_spec": {
                    "image_uri": gcr_image_uri,
                    "args": [
                        f"--task_id={task_id}",
                        f"--env={env}"
                    ],
                },
            }
        ],
    )

    await job.submit_async()
    
    output = job.to_dict()
    handler_id = output['name']
    print(f"Custom job created. Resource name: {handler_id}")

    return handler_id


async def poll_job_status(handler_id):
    while True:
        job = await aiplatform.CustomJob.get_async(handler_id)
        status = job.state
        if status is None:
            status_str = "UNKNOWN"
        elif status == aiplatform.gapic.JobState.JOB_STATE_SUCCEEDED:
            status_str = "COMPLETED"
        elif status == aiplatform.gapic.JobState.JOB_STATE_FAILED:
            status_str = "ERROR"
        elif status == aiplatform.gapic.JobState.JOB_STATE_CANCELLED:
            status_str = "CANCELLED"
        elif status == aiplatform.gapic.JobState.JOB_STATE_RUNNING:
            status_str = "RUNNING"
        elif status == aiplatform.gapic.JobState.JOB_STATE_PENDING:
            status_str = "PENDING"
        else:
            status_str = str(status)

        if status_str in ["COMPLETED", "ERROR", "CANCELLED"]:
            return status_str

        time.sleep(20)


async def cancel_job(job_id):
    try:
        job = await aiplatform.CustomJob.get_async(job_id)
        await job.cancel_async()
        print(f"Job {job_id} cancellation requested.")
        return True
    except Exception as e:
        print(f"Error canceling job {job_id}: {str(e)}")
        return False
