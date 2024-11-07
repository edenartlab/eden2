import os
import asyncio
import random
import replicate
from bson import ObjectId
from pydantic import Field
from typing import Dict, Optional
from datetime import datetime

import s3
import eden_utils
from models import Task, User, Model
from tool import Tool


class ReplicateTool(Tool):
    model: str
    version: Optional[str] = Field(None, description="Replicate version to use")
    output_handler: str = "normal"
    
    @Tool.handle_run
    async def async_run(self, args: Dict, env: str):
        args = self._format_args_for_replicate(args)
        if self.version:
            prediction = self._create_prediction(args, webhook=False)        
            prediction.wait()
            if self.output_handler == "eden":
                result = {"output": prediction.output[-1]["files"][0]}
            elif self.output_handler == "trainer":
                result = {
                    "output": prediction.output[-1]["files"][0],
                    "thumbnail": prediction.output[-1]["thumbnails"][0]
                }
            else:
                result = {"output": prediction.output}
        else:
            result = {
                "output": replicate.run(self.model, input=args)
            }
        result = eden_utils.upload_result(result, env=env)
        return result

    @Tool.handle_start_task
    async def async_start_task(self, task: Task, webhook: bool = True):
        args = self.prepare_args(task.args)
        args = self._format_args_for_replicate(args)
        if self.version:
            prediction = self._create_prediction(args, webhook=webhook)
            return prediction.id
        else:
            # Replicate doesn't allow spawning tasks for models without a public version ID.
            # So just get run and finish task immediately
            output = replicate.run(self.model, input=task.args)
            replicate_update_task(task, "succeeded", None, output, "normal")
            handler_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=28))  # make up a fake Replicate id
            return handler_id

    @Tool.handle_wait
    async def async_wait(self, task: Task):
        if self.version is None:
            return task.result
        else:
            prediction = await replicate.predictions.async_get(task.handler_id)
            status = "starting"
            while True: 
                if prediction.status != status:
                    status = prediction.status
                    result = replicate_update_task(
                        task,
                        status, 
                        prediction.error, 
                        prediction.output, 
                        self.output_handler
                    )
                    if result["status"] in ["failed", "cancelled", "completed"]:
                        return result["result"]
                await asyncio.sleep(0.5)
                prediction.reload()

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        try:
            prediction = replicate.predictions.get(task.handler_id)
            prediction.cancel()
        except Exception as e:
            print("Replicate cancel error, probably task is timed out or already finished", e)

    async def async_run_task_and_wait(self, task: Task):
        await self.async_start_task(task, webhook=False)
        result = await self.async_wait(task)
        return result

    def _format_args_for_replicate(self, args: dict):
        new_args = args.copy()
        new_args = {k: v for k, v in new_args.items() if v is not None}
        for key, param in self.base_model.model_fields.items():
            metadata = param.json_schema_extra or {}
            is_array = metadata.get('is_array')
            alias = metadata.get('alias')
            if is_array:
                new_args[key] = "|".join([str(p) for p in args[key]])
            if alias:
                new_args[alias] = new_args.pop(key)
        return new_args

    def _create_prediction(self, args: dict, webhook=True):
        user, model = self.model.split('/', 1)
        webhook_url = get_webhook_url() if webhook else None
        webhook_events_filter = ["start", "completed"] if webhook else None

        if self.version == "deployment":
            deployment = replicate.deployments.get(f"{user}/{model}")
            prediction = deployment.predictions.create(
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        else:
            model = replicate.models.get(f"{user}/{model}")
            version = model.versions.get(self.version)
            prediction = replicate.predictions.create(
                version=version,
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        return prediction


def get_webhook_url():
    env = "tools" if os.getenv("ENV") == "PROD" else "tools-dev"
    dev = "-dev" if os.getenv("ENV") == "STAGE" and os.getenv("MODAL_SERVE") == "1" else ""
    webhook_url = f"https://edenartlab--{env}-fastapi-app{dev}.modal.run/update"
    return webhook_url


def replicate_update_task(task: Task, status, error, output, output_handler):
    if status == "failed":
        task.update(status="failed", error=error)
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.from_id(task.user, env=task.env)
        user.refund_manna(refund_amount)
        return {"status": "failed", "error": error}
    
    elif status == "canceled":
        task.update(status="cancelled")
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.from_id(task.user, env=task.env)
        user.refund_manna(refund_amount)
        return {"status": "cancelled"}
    
    elif status == "processing":
        task.performance["waitTime"] = (datetime.utcnow() - task.createdAt).total_seconds()
        task.status = "running"
        task.save()
        return {"status": "running"}
    
    elif status == "succeeded":
        if output_handler == "normal":
            output = output if isinstance(output, list) else [output]
            result = eden_utils.upload_media(output, env=task.env)
        
        elif output_handler in ["trainer", "eden"]:
            result = replicate_process_eden(output, env=task.env)

            if output_handler == "trainer":
                filename = result[0]["filename"]
                thumbnail = result[0]["thumbnail"]
                url = f"{s3.get_root_url(env=task.env)}/{filename}"
                model = Model(
                    name=task.args["name"],
                    user=task.user,
                    task=task.id,
                    thumbnail=thumbnail,
                    args=task.args,
                    checkpoint=url, 
                    base_model="sdxl",
                    env=task.env
                )
                model.save(upsert_query={"task": ObjectId(task.id)})  # upsert_query prevents duplicates
                result[0]["model"] = model.id
        
        run_time = (datetime.utcnow() - task.createdAt).total_seconds()
        if task.performance.get("waitTime"):
            run_time -= task.performance["waitTime"]
        task.performance["runTime"] = run_time
        
        task.status = "completed"
        task.result = result
        task.save()

        return {
            "status": "completed", 
            "result": result
        }


def replicate_process_eden(output, env):
    output = output[-1]
    if not output or "files" not in output:
        raise Exception("No output found")         

    results = []
    
    for file, thumb in zip(output["files"], output["thumbnails"]):
        file_url, _ = s3.upload_file_from_url(file, env=env)
        filename = file_url.split("/")[-1]
        metadata = output.get("attributes")
        media_attributes, thumbnail = eden_utils.get_media_attributes(file_url)

        result = {
            "filename": filename,
            "metadata": metadata,
            "mediaAttributes": media_attributes
        }

        thumbnail = thumbnail or thumb or None
        if thumbnail:
            thumbnail_url, _ = s3.upload_file_from_url(thumbnail, file_type='.webp', env=env)
            result["thumbnail"] = thumbnail_url

        results.append(result)

    return results
    