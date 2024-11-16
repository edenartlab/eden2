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
        new_message = UserMessage(content="animate the last picture with runway. then with musicgen, make an appropriate soundtrack of the same length as the video. then use the audio video combination tool to put them together into a single video with sound.")
        # new_message = UserMessage(content="good now take the last thing and make a musicgen soundtrack the same duration as the movie, and then use the audio video combination tool to put them together into a single video with sound.")
        # new_message = UserMessage(content="make a picture of a fancy cat. just do it, be creative.")
        thread.add_messages(new_message)
        thread.save()
    
    # except Exception as e:
    #     print("ERROR", e)
    #     raise e

    stop = False
    while not stop:
        stop = await run_thread(thread)
    print("STOP!")


if __name__ == "__main__":
    asyncio.run(main())

