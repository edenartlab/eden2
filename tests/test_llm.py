import os

from eve.llm import prompt_thread, UserMessage, AssistantMessage
from eve.tool import get_tools_from_mongo


# todo: since prompt_thread handles exceptions, this won't actually fail if there are errors
def test_prompting():
    user_id = os.getenv("EDEN_TEST_USER_STAGE")
    for msg in prompt_thread(
        db="STAGE",
        user_id=user_id, 
        agent_id="67069a27fa89a12910650755",
        thread_id=None,#"test_cli5", 
        user_messages=[UserMessage(content="can you make a picture of a fancy dog with flux_schnell? and then remix it.")], 
        tools=get_tools_from_mongo(db="STAGE")
    ):
        print(msg)

# test_prompting()


def test_prompting2():
    user_id = os.getenv("EDEN_TEST_USER_STAGE")

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
        UserMessage(name="morgan", content="what is even going on here? im so confused."),
        UserMessage(name="scott", content=""),
        AssistantMessage(content="", tool_calls=[
            {
                "id": "toolu_0133ZrxH9yYsGSDJdDEkPeio",
                "tool": "flux_dev",
                "args": {
                    "prompt": "make a picture of a fancy dog with flux_schnell? and then remix it."
                },
                "db": "STAGE",
                "status": "completed",
                "result": [
                    {"output": [{
                        "url": "https://example.com/image.png"
                    }]}
                ],
                "error": None
            }
        ]),
        # UserMessage(name="kate", content="what did morgan say?"),
        UserMessage(name="kate", content="what is my name?"),
    ]


    for msg in prompt_thread(
        db="STAGE",
        user_id=user_id, 
        agent_id="67069a27fa89a12910650755",
        thread_id=None,#"test_cli5", 
        user_messages=messages,
        tools=get_tools_from_mongo(db="STAGE"),
        provider="anthropic",
    ):
        print(msg)

    # thread.push("messages", messages[2])
    # thread.save()
    # thread.messages = messages

    # content, tool_calls, stop = await async_openai_prompt(
    #     thread.messages, 
    #     tools=tools
    # )
    # print(content)
    # print(tool_calls)
    # print(stop)



test_prompting2()