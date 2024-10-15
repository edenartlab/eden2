import sys
sys.path.append("../..")

from agent import Agent
from mongo import get_collection
from bson import ObjectId
from thread import UserMessage, async_prompt, Thread


async def chat(args: dict, user: str = None, env: str = "STAGE"):
    agent = Agent.from_id(args["agent_id"], env=env)

    if args["thread_id"]:
        threads = get_collection("threads", env=env)
        thread = threads.find_one({"_id": ObjectId(args["thread_id"])})
        if not thread:
            raise Exception("Thread not found")
        thread = Thread.from_id(args["thread_id"], env=env)
    else:
        print("creating new thread")
        thread = Thread(env=env, user=user)
        thread.save()  # this should be encapsulated
        print("thread created")
        print(user)

    message = UserMessage(
        content=args["content"],
        attachments=args["attachments"]
    )

    results = [
        response.model_dump_json() 
        async for response in async_prompt(thread, agent, message)
    ]
    print("results", results)
        
    return {"messages": results}





"""
class ChatTool(Tool):

    @Tool.handle_run
    async def async_run(self, args: Dict):
        print("args", args) # args {'content': 'Hi, who are you?', 'attachments': []}
        
        from agent import Agent
        from mongo import get_collection
        from bson import ObjectId
        from thread import UserMessage, async_prompt, Thread

        agent = Agent.from_id(args["agent_id"], env=env)
        print("agent", agent)
        if args["thread_id"]:
            threads = get_collection("threads", env=env)
            thread = threads.find_one({"_id": ObjectId(args["thread_id"])})
            if not thread:
                raise Exception("Thread not found")
            thread = Thread.from_id(args["thread_id"], env=env)
        else:
            thread = Thread(env=env)

        message = UserMessage(
            content=args["content"],
            attachments=args["attachments"]
        )
        print("message", message)

        # result = prompt(thread, agent, message)
        # print("result!!!", result)
        results = []
        async for response in async_prompt(thread, agent, message):
            results.append(response.model_dump_json())
            
        # output = ["https://edenartlab-prod-data.s3.us-east-1.amazonaws.com/bb88e857586a358ce3f02f92911588207fbddeabff62a3d6a479517a646f053c.jpg"]
        # result = eden_utils.upload_media(output, env=env)
        return results
        
    @Tool.handle_submit
    async def async_submit(self, task: Task, webhook: bool = True):
        task.handler_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=28))
        task.status = "pending"
        task.save()
        return task.handler_id

    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()
        result = await self.async_run(task.args)
        task.status = "completed"
        task.result = result
        task.save()
        # return self.get_user_result(result)
        return result

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        print("Unimplemented")
"""