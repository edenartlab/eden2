import os

from eve.llm import prompt_thread, UserMessage
from eve.tool import get_tools_from_mongo


# todo: since prompt_thread handles exceptions, this won't actually fail if there are errors
def test_prompting():
    user_id = os.getenv("EDEN_TEST_USER_STAGE")
    result = prompt_thread(
        db="STAGE",
        user_id=user_id, 
        thread_name="test_cli5", 
        user_messages=UserMessage(content="can you make a picture of a fancy dog with flux_schnell? and then remix it."), 
        tools=get_tools_from_mongo(db="STAGE")
    )
    print(result)



"""

# todo: test message orderings
async def test2():
    thread = Thread(db="STAGE", name="test_cli6", user=ObjectId(user_id))
    messages = [
        UserMessage(content="hi there!!."),
        UserMessage(content="do you hear me?"),
        UserMessage(content="Hello, tell me something now."),
        AssistantMessage(content="I have a cat."),
        AssistantMessage(content="Apples are bananers."),
        UserMessage(content="what did you just say? repeat everything you said verbatim."),
        UserMessage(content="hello?"),
        AssistantMessage(content="I said Apples are bananers."),
        UserMessage(content="no"),
        UserMessage(content="you said something before that"),
    ]

    messages = [
        UserMessage(name="jim", content="i have an apple."),
        UserMessage(name="kate", content="the capital of france is paris?"),
        UserMessage(name="morgan", content="what is even going on here?"),
        UserMessage(name="scott", content="i am you?"),
        UserMessage(content="what did morgan say?"),
    ]

    thread.push("messages", messages[2])
    thread.save()
    # thread.messages = messages

    content, tool_calls, stop = await async_openai_prompt(
        thread.messages, 
        tools=tools
    )
    print(content)
    print(tool_calls)
    print(stop)

"""