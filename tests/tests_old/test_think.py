import os
import sys
sys.path.append(".")
env = os.getenv("ENV")

from bson import ObjectId
from agent import get_default_agent
from tool import get_tools
from thread import Thread, UserMessage, prompt

#tools = get_tools("../workflows/workspaces")
tools = get_tools("tools")
user = ObjectId("65284b18f8bbb9bff13ebe65")  # user = gene3
agent = get_default_agent() # eve

thread = Thread.from_name("test57", user, env=env, create_if_missing=True)


"""

Covenant
 - Every day, Abraham drafts 10 stories, and animates 1.
 - Every Sunday, a Miracle occurs and Manna rains from the heavens.
 - 


There are currently 10 proposed stories. They are the following:
* Story1 (1250 manna)
 - 16 praises, 4 burns
 - 5 blessings
    * jmill: this is amazing
* Story2 (716 manna)

"""
import json

from models import Story

story = Story.from_id("66de2dfa5286b9dc656291c1", env=env)
story_state = f"{json.dumps(story.current, indent=2)}"



"""

"""



prompt = "change the visual style to gothic"
prompt = "make Todd interested in science and technology, not art and design"

system_message = "You are an expert at crafting stories."

content = f"""## Instructions

You are currently crafting a story. The user will give you some feedback or a request to change or add to the story somehow. You can use the `write` tool to make edits to the story.

Follow these guidelines:
* Try to make the minimum possible changes to the story to incorporate the new request. If the user asks to change the visual style, you do not necessarily need to change the summary or scenes. Only do so if the user specifically requests it or if the change requested requires a change to the summary or scenes. Default to minimal edits.
* Leave blank any fields which you are not changing.

## Current Story

{story_state}

---
## Prompt from user

{prompt}
"""

print("---")
print(content)
print("---")
print(len(tools))
from thread import *

messages = [UserMessage(content=content)]

message_content, tool_calls, _ = anthropic_prompt(messages, system_message, tools)


print(message_content)
print(json.dumps(tool_calls[0].model_dump(), indent=2))



# user_message = UserMessage(
#     content="whats your name? who made you?", 
# )
# for message in prompt(thread, agent, user_message, provider="anthropic", auto_save=False):
#     print(message)


# print(thread.messages)
