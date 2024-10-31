# import sys
# sys.path.append('..')

from tool import Tool


from pydantic import Field
from typing import List, Optional

from models import Task
from typing import Dict
from functools import wraps
import modal
from datetime import datetime

import replicate
import random

import s3

from models import Task, User


env="STAGE"


def task_handler2(func):
    @wraps(func)
    async def wrapper(task_id: str, env: str):
        task = Task.load(task_id, env=env)
        print(task)
        
        start_time = datetime.utcnow()
        queue_time = (start_time - task.createdAt).total_seconds()
        
        task.update(
            status="running",
            performance={"waitTime": queue_time}
        )

        try:
            result = await func(task.workflow, task.args, task.user, env=env)
            task_update = {
                "status": "completed", 
                "result": result
            }
            return task_update

        except Exception as e:
            print("Task failed", e)
            task_update = {"status": "failed", "error": str(e)}
            user = User.load(task.user, env=env)
            user.refund_manna(task.cost or 0)

        finally:
            run_time = datetime.utcnow() - start_time
            task_update["performance"] = {
                "waitTime": queue_time,
                "runTime": run_time.total_seconds()
            }
            task.update(**task_update)

    return wrapper


from pprint import pprint
import eden_utils

def task_handler(func):
    @wraps(func)
    async def wrapper(task_id: str, env: str):
        task = Task.load(task_id, env=env)
        print(task)
        
        start_time = datetime.utcnow()
        queue_time = (start_time - task.createdAt).total_seconds()
        #boot_time = queue_time - self.launch_time if self.launch_time else 0
        
        task.update(
            status="running",
            performance={"waitTime": queue_time}
        )

        result = []
        n_samples = task.args.get("n_samples", 1)
        pprint(task.args)
        
        try:
            for i in range(n_samples):
                args = task.args.copy()
                if "seed" in args:
                    args["seed"] = args["seed"] + i

                output, intermediate_outputs = await func(task.workflow, args, env=env)
                print("intermediate_outputs", intermediate_outputs)

                result_ = eden_utils.upload_media(output, env=env)
                if intermediate_outputs:
                    result_[0]["intermediateOutputs"] = {
                        k: eden_utils.upload_media(v, env=env, save_thumbnails=False)
                        for k, v in intermediate_outputs.items()
                    }
                
                result.extend(result_)

                if i == n_samples - 1:
                    task_update = {
                        "status": "completed", 
                        "result": result
                    }
                else:
                    task_update = {
                        "status": "running", 
                        "result": result
                    }
                    task.update(task_update)
    
            return task_update

        except Exception as e:
            print("Task failed", e)
            task_update = {"status": "failed", "error": str(e)}
            refund_amount = (task.cost or 0) * (n_samples - len(result)) / n_samples
            user = User.from_id(task.user, env=env)
            user.refund_manna(refund_amount)

        finally:
            run_time = datetime.utcnow() - start_time
            task_update["performance"] = {
                "waitTime": queue_time,
                "runTime": run_time.total_seconds()
            }
            task.update(**task_update)
            #self.launch_time = 0

    return wrapper


import asyncio
import replicate


class ReplicateTool(Tool):
    model: str
    version: Optional[str] = Field(None, description="Replicate version to use")
    output_handler: str = "normal"
    
    @Tool.handle_run
    async def async_run(self, args: Dict):        
        args = prepare_args(args, self)
        if self.version:
            prediction = _create_prediction(args, webhook=False)        
            prediction.wait()
            if self.output_handler == "eden":
                output = [prediction.output[-1]["files"][0]]
            elif self.output_handler == "trainer":
                output = [prediction.output[-1]["thumbnails"][0]]
            else:
                output = prediction.output if isinstance(prediction.output, list) else [prediction.output]
                output = [url for url in output]
        else:
            output = replicate.run(self.model, input=args)
        env="STAGE"
        result = eden_utils.upload_media(output, env=env)
        return result

    # @Tool.handle_submit
    async def async_submit(self, task: Task, webhook: bool = True):
        args = prepare_args(task.args, self)
        if self.version:
            prediction = _create_prediction(self, args, webhook=webhook)
            return prediction.id
        else:
            # Replicate doesn't support spawning tasks for models without a version so just get results immediately
            output = replicate.run(self.model, input=task.args)
            replicate_update_task(task, "succeeded", None, output, "normal")
            handler_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=28))  # make up Replicate id
            return handler_id

    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()

        if self.version is None:
            return self.get_user_result(task.result)        
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
                        return self.get_user_result(result["result"])
                await asyncio.sleep(0.5)
                prediction.reload()

    async def async_submit_and_run(self, task: Task):
        await self.async_submit(task, webhook=False)
        result = await self.async_process(task)
        return result

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        try:
            prediction = replicate.predictions.get(task.handler_id)
            prediction.cancel()
        except Exception as e:
            print("Replicate cancel error, probably task is timed out or already finished", e)


import os

def _prepare_args(args, tool):
    new_args = args.copy()
    new_args = {k: v for k, v in new_args.items() if v is not None}
    for key, param in tool.base_model.__fields__.items():
        metadata = param.json_schema_extra or {}
        is_array = metadata.get('is_array')
        alias = metadata.get('alias')
        if is_array:
            new_args[param.name] = "|".join([str(p) for p in args[key]])
        if alias:
            new_args[alias] = new_args.pop(key)
    return new_args

def get_webhook_url():
    env = "tools" if os.getenv("ENV") == "PROD" else "tools-dev"
    dev = "-dev" if os.getenv("ENV") == "STAGE" and os.getenv("MODAL_SERVE") == "1" else ""
    webhook_url = f"https://edenartlab--{env}-fastapi-app{dev}.modal.run/update"
    return webhook_url

def create_prediction(tool: ReplicateTool, args: dict, webhook=True):
    user, model = tool.model.split('/', 1)
    webhook_url = get_webhook_url() if webhook else None
    webhook_events_filter = ["start", "completed"] if webhook else None

    if tool.version == "deployment":
        deployment = replicate.deployments.get(f"{user}/{model}")
        prediction = deployment.predictions.create(
            input=args,
            webhook=webhook_url,
            webhook_events_filter=webhook_events_filter
        )
    else:
        model = replicate.models.get(f"{user}/{model}")
        version = model.versions.get(tool.version)
        prediction = replicate.predictions.create(
            version=version,
            input=args,
            webhook=webhook_url,
            webhook_events_filter=webhook_events_filter
        )
    return prediction


def replicate_update_task(task: Task, status, error, output, output_handler):
    if status == "failed":
        task.status = "error"
        task.error = error
        task.save()
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result)) / n_samples
        user = User.from_id(task.user, env=env)
        user.refund_manna(refund_amount)
        return {"status": "failed", "error": error}
    
    elif status == "canceled":
        task.status = "cancelled"
        task.save()
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result)) / n_samples
        user = User.from_id(task.user, env=env)
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
            result = eden_utils.upload_media(output, env=env)
        
        elif output_handler in ["trainer", "eden"]:
            result = replicate_process_eden(output)

            if output_handler == "trainer":
                filename = result[0]["filename"]
                thumbnail = result[0]["thumbnail"]
                url = f"{s3.get_root_url(env=env)}/{filename}"
                model = Model(
                    name=task.args["name"],
                    user=task.user,
                    args=task.args,
                    task=task.id,
                    checkpoint=url, 
                    base_model="sdxl",
                    thumbnail=thumbnail,
                    env=env
                )
                # model.save()
                model.save({"task": task.id})
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


def replicate_process_eden(output):
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
    