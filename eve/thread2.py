from eve.tool import get_tools_from_mongo
tools = get_tools_from_mongo(env="STAGE")

print(tools)

t = tools['txt2img']

tools = {k: v for k, v in tools.items() if k in ["txt2img", "animate_3D"]}

from eve.thread import UserMessage, AssistantMessage
from eve.llm import anthropic_prompt

messages = [
    UserMessage(content="Hello, how are you?"),
    AssistantMessage(content="I'm good, thanks for asking."),
    UserMessage(content="Can you make a video of a fancy cat ?")
]

print(messages)

result = anthropic_prompt(messages, "You are a helpful assistant.", tools=tools)

print(result)


"""
ToolCall
- result

UserMessage
AssistantMessage
 - reply_to: UserMessage
 - tool calls

 
anthropic
- UserMessage
- AssistantMessage (reply_to: UserMessage)
  - tool calls ( + result)

before reply, just use dummy message

user
assistant
tool
user
assistant

user
user







"""