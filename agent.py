from mongo import MongoBaseModel#, mongo_client
from typing import List


class Agent(MongoBaseModel):
    name: str
    description: str
    instructions: str
    tools: List[str]

    def __init__(self, env, **data):
        super().__init__(collection_name="agents", env=env, **data)

    @classmethod
    def from_id(self, document_id: str, env: str):
        return super().from_id(self, document_id, "agents", env)

    def get_system_message(self):
        system_message = f"{self.description}\n\n{self.instructions}\n\n{generic_instructions}"
        print("system_message", system_message)
        return system_message


generic_instructions = """Follow these additional guidelines:
- If the tool you are using has the "n_samples" parameter, and the user requests for multiple versions of the same thing, set n_samples to the number of images the user desires for that prompt. If they want N > 1 images that have different prompts, then make N separate tool calls with n_samples=1.
- When a lora is set, absolutely make sure to include "<concept>" in the prompt to refer to object or person represented by the lora.
- If you get an error using a tool because the user requested an invalid parameter, or omitted a required parameter, ask the user for clarification before trying again. Do *not* try to guess what the user meant.
- If you get an error using a tool because **YOU** made a mistake, do not apologize for the oversight or explain what *you* did wrong, just fix your mistake, and automatically retry the task.
- When returning the final results to the user, do not include *any* text except a markdown link to the image(s) and/or video(s) with the prompt as the text and the media url as the link. DO NOT include any other text, such as the name of the tool used, a summary of the results, the other args, or any other explanations. Just [prompt](url).
- When doing multi-step tasks, present your intermediate results in each message before moving onto the next tool use. For example, if you are asked to create an image and then animate it, make sure to return the image (including the url) to the user (as markdown, like above)."""