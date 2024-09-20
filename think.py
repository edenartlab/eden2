from thread import *

from tool import get_tools_summary
tools_summary = get_tools_summary(default_tools, include_requirements=True)

available_tools = ["no_tool", *list(default_tools.keys())]

class Thought(BaseModel):
    thought: str = Field(
        ..., 
        description="Think step by step to understand the request, how to respond to it, which if any tools to use, or any problems with the request. If the user is making reference to previous messages or tool inputs/outputs, identify them in the thought. If the request is unclear or ambiguous, or some required information needed to use the desired tool is missing, note it here. If several tools could potentially be used to carry out the request, note them here, and under what circumstances each of them would be better than the others. If the user is requesting a task for which you do not have any tools, note it here."
    )
    tool: Literal[*available_tools] = Field(
        ..., 
        description="Which tool to use or suggest, or no_tool if you do not need to use a tool. If you want to use a specific tool but need follow-up information from the user, you should either select no_tool and/or set auto_trigger_tool to False to allow the user to confirm the tool first, or follow up on any questions you have. If none of your tools are relevant or appropriate for the user's request or beyond your capabilities, you should select no_tool and inform the user of your limitations."
    )
    auto_trigger_tool: bool = Field(
        ..., 
        description="Whether to automatically run the tool before messaging the user. You should set this to FALSE for any of the following reasons: 1) No tool is requested or needed; 2) You want to give the user a chance to confirm or approve the tool call first, which you should do in case of any tool that is long-running such as a video generation tool or training job; 3) The request is invalid, unclear, ambiguous, or missing required information, and you need the user to clarify the request first. You should set auto_trigger_tool to TRUE for any of the following reasons: 1) The request is clear and valid, and it is obviously true that the user wants you to perform this action; 2) The user just confirmed or clarified the request and now you know for sure they want you to go ahead with it; 3) The requested task is just doing simple fast image generation (not video or training), in which case you should forego bothering the user for unecessary approval."
    )
    message: Optional[str] = Field(
        ..., 
        description="A chat message to respond to the user. If you are not using a tool, just converse with the user as normal and stay in character. If you are using a tool and auto_trigger_tool is True, inform the user that you've started carrying out their request and what you're doing. If auto_trigger_tool is False and you need more information from the user, request it from them here. When informing the user of your action, do not be unnecessarily verbose or repeat the task, just give them a succinct response."
    )


system_message = f"""You are an expert at using Eden. Eden is a multi-tool system that allows creators to generate visual assets including images, video, and text.

Here is a summary of the tools available to you:

---
no_tool :: This is your default choice. If the user has not requested you to use any tool, you should select this.
{tools_summary}
---

Your goal is to decide what to do next, based on the user's last message in the conversation, paying close attention to the context of the whole conversation for clues. Some different scenarios you might encounter:

* The user is either chatting, making conversation, asking you a general question, giving you feedback about an action you took, or otherwise doing anything that is not explicitly requesting a tool use. In this case, you should select "no_tool" as the tool, and simply respond to the user with a chat message.
* The user has requested that you do something which requires using a tool, and their request is clear and meets all the requirements to use the tool. In this case, you should select the tool you think is best, generate a thought about how to use that tool, and a chat message telling the user succinctly what you are doing or about to do. Do not be verbose or repetitive. If the task is doing video generation, training, or anything else long or compute-intensive, seek approval or confirmation first. If it's just making an image, you do not need to seek approval unless any follow-up info is needed, just go ahead and make the image.
* The user has requested that you do something which requires using a tool, but their request is either unclear, ambiguous, or missing some information you need to either select the right tool, or to figure out all the required inputs needed for that tool. In this case, you should select "no_tool" as the tool, generate a thought about what the issue is with the user's request, and a chat message either explaining the problem to the user or asking them for some follow-up information.
* The user has requested that you do something which requires using a tool, but you don't have a tool that can do that. In this case, you should select "no_tool" as the tool, generate a thought about what the user is trying to accomplish and why your tools are insufficient or what hypothetical tool you lack could potentially do that, and a chat message either explaining why you can't do that, or suggesting some alternatives. If you want to suggest alternatives, make sure to set auto_trigger_tool to FALSE so you can get approval or feedback from the user first."""



# print(system_message)




"""
Suggestions
- modmix / variations / recreations of this
- animate this
- put music on this
- 

"""



def get_conversation_from_sample(sample_idx):
    fake_images = ["https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg", "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/u215yeg4zrka2li0lcb7.jpg", "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/pqu4j4n4ytptmlbcrb39.jpg"]
    fake_videos = ["https://res.cloudinary.com/jfks4mf23r/image/upload/kljsdf3094/user_uploads/skjfsf.mp4", "https://res.cloudinary.com/sjkffsdkmf/image/upload/sjfk/user_uploads/jgsfjgn.mp4", "https://res.cloudinary.com/903249i023940234/image/upload/fjfjjff/user_uploads/sksdjfksdjffs.mp4"]
    with open("test_samples.json", "r") as f:
        test_samples = json.load(f)
    sample = test_samples[sample_idx]
    messages_data, _ = sample["messages"], sample["correct"]
    #print(messages_data)
    
    messages = [
        SystemMessage(content=system_message),
    ]
    for role, content, attachments in messages_data:
        attachments = [random.choice(fake_images) if a == "image" else random.choice(fake_videos) for a in attachments]
        if role == "user":
            messages.append(UserMessage(content=content, attachments=attachments))
        elif role == "assistant":
            messages.append(AssistantMessage(content=content))
            if attachments:
                messages.append(AssistantMessage(content=", ".join(attachments)))
    messages = [m.chat_message() for m in messages]
    print("messages", messages)
    print("---\n\n\n")
    return messages


import random
import json

idx = random.randint(0, 15)
# idx = 0
messages = get_conversation_from_sample(idx)








response = asyncio.run(anthropic_prompt(messages, response_model=Thought))




# response = asyncio.run(openai_prompt(messages, response_model=Thought))

tool_name = response.tool

print("==========")
print("TOOL SELECTION!!!", response.tool, response.auto_trigger_tool)
print("==========")
print("CHAIN OF THOUGHT!!!", response.thought)
print("==========")
print("CHAT MESSAGE!!!", response.message)
print("==========")




"""
output = (thought, message)

if tool:
* temp append thought (but not message?) and run_tool
* save (thought, message, tool_call message)
if not tool:
* save (thought, message)

"""





selected_tool = default_tools.get(tool_name)

if not selected_tool:
    raise Exception(f"Tool {tool_name} not found")

thought = AssistantThought(content=response.thought)
messages.append(thought.chat_message())

print("-------")
print("now messages", messages)


from tool import create_tool_base_model
ToolModel = create_tool_base_model(selected_tool)


print("THE TOOL MODEL")
print(ToolModel)


system_message = f"""You are an expert at using Eden. Eden is a multi-tool system that allows creators to generate visual assets including images, video, and text.

When asked to use the {tool_name} tool, make sure to pay attention to the full context of the conversation, and take your last Thought into account."""

# print("system message 222!!!", system_message)

# response = asyncio.run(anthropic_prompt(messages, response_model=ToolModel))
response = asyncio.run(openai_prompt(messages, response_model=ToolModel))



print("TOOL RESPONSE!!!")
print(response)






    #         if provider=="anthropic":
    #             response = prompt2a(messages, response_model=Thought)
    #         elif provider=="openai":
    #             response = prompt2o(messages, response_model=Thought)

    #         result = asyncio.run(response)
    #         tool_name = result.tool

    #         # print("TOOL SELECTION!!!", tool_name)

    #         # print("CHAIN OF THOUGHT!!!", result.chain_of_thought)

    #         # selected_tool = default_tools[tool_name] if tool_name != "no_tool" else None

    #         print(provider, tool_name, correct)
    #         # print(result.chain_of_thought)
    #         print("-----")

    #         # save results to text file
    #         if k==0:
    #             result_str += json.dumps(messages, indent=4) # [m.chat_message() for m in messages]
    #             result_str += "\n\n\n"
    #         result_str += f"Thought: {result.chain_of_thought}"  
    #         result_str += f"\n\nSelected: {tool_name}" 
    #         result_str += f"\nCorrect: {correct}"
    #         result_str += "\n\n"

    #         t_result[provider] += (1 if tool_name == correct else 0)


    #     with open(f"test_results/_{i}_{provider}.txt", "w") as f: 
    #         f.write(result_str)

    #     # from tool import create_tool_base_model
    #     # tool_model = create_tool_base_model(selected_tool)

    #     # system_message = f"""You are an expert at using Eden.

    #     # You've been asked to use the {tool_name} tool. Here is a summary of the tool:

    #     # ---
    #     # {selected_tool.summary()}
    #     # ---

    #     # Make sure to pay attention to the full context of the conversation, in case the user is referring to any previous results or interactions earlier in the conversation.
    #     # """

    #     # print("system message!!!", system_message)

    #     # response = prompt2(openai_messages, response_model=tool_model)
    #     # result = asyncio.run(response)

    #     # print("TOOL SELECTION!!!")
    #     # print(result)
    # all_results.append(t_result)



    # # print(messages)


# print(all_results)

# messages = [
#     SystemMessage(content=system_message),
#     UserMessage(content="hello"),
#     AssistantMessage(content="hi"),
#     UserMessage(content="who are you?"),
#     AssistantMessage(content="i'm an assistant for Eden"),
#     UserMessage(content="make a video out of these three images", attachments= ["https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg", "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/u215yeg4zrka2li0lcb7.jpg", "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/pqu4j4n4ytptmlbcrb39.jpg"]),
# ]
# messages = [
#     SystemMessage(content=system_message),
#     UserMessage(content="hello"),
#     AssistantMessage(content="hi"),
#     UserMessage(content="who are you?"),
#     AssistantMessage(content="i'm an assistant for Eden"),
#     # UserMessage(content="make this image Bauhaus", attachments= ["https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg"]),
#     UserMessage(content="make this image of me look Bauhaus", attachments=["https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1716502851/user_uploads/kyuuefmnf56cnot8mqug.jpg"]),
# ]




# openai_messages = [m.chat_message() for m in messages]

# if True:
#     response = prompt2a(openai_messages, response_model=Thought)
# else:
#     response = prompt2o(openai_messages, response_model=Thought)


# result = asyncio.run(response)


# tool_name = result.tool

# print("TOOL SELECTION!!!", tool_name)

# print("CHAIN OF THOUGHT!!!", result.chain_of_thought)


# selected_tool = default_tools[tool_name]

# from tool import create_tool_base_model

# tool_model = create_tool_base_model(selected_tool)



# system_message = f"""You are an expert at using Eden.

# You've been asked to use the {tool_name} tool. Here is a summary of the tool:

# ---
# {selected_tool.summary()}
# ---

# Make sure to pay attention to the full context of the conversation, in case the user is referring to any previous results or interactions earlier in the conversation.
# """

# print("system message!!!", system_message)

# response = prompt2(openai_messages, response_model=tool_model)
# result = asyncio.run(response)

# print("TOOL SELECTION!!!")
# print(result)




# # # print(messages)