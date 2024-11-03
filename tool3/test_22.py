from functools import wraps

class Task:
    def __init__(self, workflow, args, env):
        self.workflow = workflow
        self.args = args
        self.env = env


async def _task_handler_core(func, *args, **kwargs):
    # Pre-processing logic
    print("Starting pre-processing")
    
    # Unpack `Task` if passed as a keyword or positional argument
    task = kwargs.pop("task", args[-1])
    if not isinstance(task, Task):
        raise ValueError("Expected Task instance as last argument or `task=` keyword.")
    
    # Prepare arguments
    workflow, task_args, env = task.workflow, task.args, task.env
    
    # Call the actual function
    result = await func(*args[:-1], workflow, task_args, env=env, **kwargs)
    
    # Post-processing logic
    print("Starting post-processing")
    
    return result

def task_handler_func(func):
    """Decorator for standalone functions."""
    @wraps(func)
    async def wrapper(task: Task):
        return await _task_handler_core(func, task)
    return wrapper

def task_handler_method(func):
    """Decorator for class methods."""
    @wraps(func)
    async def wrapper(self, task: Task):
        return await _task_handler_core(func, self, task)
    return wrapper



@task_handler_func
async def run_task(tool_key: str, args: dict, env: str):
    print("standalone runtask")
    print(tool_key, args, env)
    return {"output": "that was a test"}

class ComfyUI:
    def _execute(self, workflow_name: str, args: dict, env: str):
        print(workflow_name, args, env)
        output = {"output": "that was a test"}
        return output

    @task_handler_method
    async def run_task(self, tool_key: str, args: dict, env: str):
        print("comfyui runtask")
        print(tool_key, args, env)
        return {"output": "that was a test"}
    


async def main():
    # Create a Task instance for testing
    task_instance = Task("test_workflow", {"test": "test_args"}, "STAGE")

    # For the class method, call with the created task instance
    print("================")
    await ComfyUI().run_task(task_instance)
    print("================")

    print("now standalone")
    # For the standalone function, also call with the task instance
    await run_task(task_instance)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())