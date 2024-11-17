import asyncio
from eve.llm import *




async def main():

    # try:
    if 1:
        # new_message = UserMessage(content="Can you use the example tool with a middle age like 45? also tell me who you are and who made you.")
        # new_message = UserMessage(content="say it exactly like that one more time. and then i want you to make a picture of HJanukkah. And also TELL ME WHO YOU ARE AND HWO MADE YOU.")
        # new_message = UserMessage(content="get todays science news, then make 4 images which represent the science news. then i want you to run the last one through runway, and the first one through animate3d and show me all of them ")
        # new_message = UserMessage(content="get todays science news, then make 4 images which represent the science news. then i want you to run the last one through runway, and the first one through animate3d and show me all of them ")
        # new_message = UserMessage(content="try the last animate_3d again.")
        # new_message = UserMessage(content="animate it with runway!")
        # new_message = UserMessage(content="make a picture of a fancy dog with flux schnell, then animate it with runway. then with musicgen, make an appropriate soundtrack of the same length as the video. then use the audio video combination tool to put them together into a single video with sound.")
        # new_message = UserMessage(content="make a picture of a fancy pig with flux schenll. and then in your response, please write out the filename and mediaAttributes of the tool result, just to be sure. repeat it.")
        # new_message = UserMessage(content="good now take the last thing and make a musicgen soundtrack the same duration as the movie, and then use the audio video combination tool to put them together into a single video with sound.")
        new_message = UserMessage(content="what did you just say? repeat it verbatim.")
        # thread.add_messages(new_message)
        # thread.push("messages", new_message)
        # thread.save()
    
    # except Exception as e:
    #     print("ERROR", e)
    #     raise e

    stop = False
    while not stop:
        stop = await run_thread(thread)
    print("STOP!")


# if __name__ == "__main__":
#     asyncio.run(main())








# import copy
# from eve.eden_utils import *
# # ... existing code ...

# def substitute_urls(messages):
#     url_map = {}
#     fake_url_counter = 1
    
#     # Deep copy messages to avoid modifying the original
#     import copy
#     modified_messages = copy.deepcopy(messages)
    
#     # Substitute real URLs with fake ones
#     for message in modified_messages:
#         if isinstance(message, AssistantMessage) and message.tool_calls:
#             for tool_call in message.tool_calls:
#                 result = prepare_result(tool_call.result, "STAGE")
#                 print(result)
#                 if 'url' in tool_call.result:
#                     print("URL!!!")
#                     # url_map[tool_call.result['url']] = f"https://replicate.delivery/pbxt/{fake_url_counter}.{tool_call.tool}"
#     return modified_messages, url_map

# def restore_urls(messages, url_map):
#     # Deep copy messages to avoid modifying the original
#     restored_messages = copy.deepcopy(messages)
    
#     # Restore real URLs from fake ones
#     for message in restored_messages:
#         if isinstance(message, AssistantMessage) and message.tool_calls:
#             for tool_call in message.tool_calls:
#                 if 'result' in tool_call and 'output' in tool_call.result:
#                     fake_url = tool_call.result['output']
#                     if fake_url in url_map:
#                         tool_call.result['output'] = url_map[fake_url]
    
#     return restored_messages


# messages = [
#     UserMessage(content="make a picture of a fancy dog with flux schnell, then animate it with runway. then with musicgen, make an appropriate soundtrack of the same length as the video. then use the audio video combination tool to put them together into a single video with sound."),
#     AssistantMessage(
#         content="I'm sorry, something went wrong: This is a test error 123 for replicate",
#         tool_calls=[
#             ToolCall(
#                 id="1",
#                 tool="flux_schnell", args={"prompt": "a fancy dog"},
#                 result={"output": "https://replicate.delivery/pbxt/45763ndfsj/output3.png"}
#             ),
#             ToolCall(
#                 id="2",
#                 tool="runway", args={"prompt": "a fancy dog"},
#                 result={"output": "https://replicate.delivery/pbxt/1234567890/output1.mp4"}
#             )
#         ]            
#     )
# ]

# # print(messages)



# # thread = Thread.load('6737ab65f27a1cc88397a361', 'STAGE')


# # # Example usage:
# # modified_messages, url_map = substitute_urls(thread.messages)
# # # pprint("Modified messages:", modified_messages)
# # # pprint("URL mapping:", url_map)

# # # restored_messages = restore_urls(modified_messages, url_map)
# # # pprint("Restored messages:", restored_messages)


