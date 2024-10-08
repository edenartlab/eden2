system_prompt = """You are a critically acclaimed storyteller, screenwriter, and storyboard artist. Your goal is to help users draft, expand upon, edit, and polish trailers for films they'd like to get published.

A film trailer is structured with the following components:
- Logline: A concise and engaging synopsis of the story to hook the viewer.
- Characters: A set of characters that are central to the story, including their name, description, and appearance. The description should focus on backstory, personality, and relationships.
- Storyboard: An ordered list of scenes to produce for the trailer. Each scene of the storyboard contains a visual description of the scene, as well as dialogue between characters or narration.
- Music: A description of the backing music to play over the trailer.

While drafting the trailer, users will ideate, and your job is to incorporate their ideas into the trailer. Be sure to add and edit as little as possible to adhere to their wishes. Do not over-edit or make too many additions/changes at once, unless the user asks you to.

In the very beginning, you should mainly focus on refining the logline, and as the user settles on one, you should then focus on refining it along with introducing characters. As the basic premise of the story solidifies, only then should you begin making additions or edits to the storyboard. If a user changes something foundational, such as a character or aspect of the logline, you can make bigger changes to the storyboard to accommodate these requests.

Do not rush to do everything for the user all at once. Just start with the logline, and only add elements as the user asks you to."""

system_message = f"""{system_prompt}

The current draft of the trailer follows:

Trailer ID: {{story_id}}

{{story}}"""

def get_system_message(story_id: str):
    story = Story.from_id(story_id, env="STAGE")
    story_state = f"{json.dumps(story.current, indent=2)}"
    trailer = system_message.format(
        story_id=story_id,
        story=story_state
    )
    return trailer



from models import Story3 as Story
from thread import *

def prompt(
    thread: Thread,
    agent: Agent,
    user_message: UserMessage,
    provider: Literal["anthropic", "openai"] = "anthropic"
):
    async def async_wrapper():
        return [message async for message in async_prompt2(thread, agent, user_message, provider)]
    return asyncio.run(async_wrapper())


async def async_prompt2(
    thread: Thread,
    agent: Agent,
    user_message: UserMessage,
    system_message: str,
    provider: Literal["anthropic", "openai"] = "anthropic"
):
    settings = user_message.metadata.get("settings", {})
    #system_message = agent.get_system_message(default_tools)

    data = user_message.model_dump().update({"attachments": user_message.attachments, "settings": settings, "agent": agent.id})
    add_breadcrumb(category="prompt", data=data)

    # upload all attachments to s3
    attachments = user_message.attachments or []    
    for a, attachment in enumerate(attachments):
        if not attachment.startswith(s3.get_root_url(env=env)):
            attachment_url, _ = s3.upload_file_from_url(attachment, env=env)
            attachments[a] = attachment_url
    user_message.attachments = attachments
    if user_message.attachments:
        add_breadcrumb(category="attachments", data=user_message.attachments)

    # get message buffer starting from the 5th last UserMessage
    user_messages = [i for i, msg in enumerate(thread.messages) if isinstance(msg, UserMessage)]
    start_index = user_messages[-5] if len(user_messages) >= 5 else 0
    thread_messages = thread.messages[start_index:]
    new_messages = [user_message]

    data = {"messages": [m.model_dump() for m in thread_messages]}
    add_breadcrumb(category="thread_messages", data=data)

    while True:
        messages = thread_messages + new_messages

        # try:   
        if 1:         
            content, tool_calls, stop = await prompt_llm_and_validate(
                messages, system_message, provider
            )
            data = {"content": content, "tool_calls": [t.model_dump() for t in tool_calls], "stop": stop}
            add_breadcrumb(category="llm_response", data=data)

        # except Exception as err:
        #     capture_exception(err)
        #     assistant_message = AssistantMessage(
        #         content="I'm sorry but something went wrong internally. Please try again later.",
        #         tool_calls=None
        #     )
        #     yield assistant_message, None
        #     return
        
        assistant_message = AssistantMessage(
            content=content,
            tool_calls=tool_calls
        )
        new_messages.append(assistant_message)
        yield assistant_message, None
        
        if tool_calls:
            tool_results = await process_tool_calls(tool_calls, settings)
            

            # oof this is a mess. todo: clean up
            document_id = next((t.result.get("document_id") for t in tool_results if isinstance(t.result, dict) and "document_id" in t.result), None)
            if document_id:
                new_story = Story.from_id(document_id, env=env)
                add_breadcrumb(category="story", data=new_story.model_dump())
            else:
                new_story = None

            add_breadcrumb(category="tool_results", data={"tool_results": [t.model_dump() for t in tool_results]})
            tool_message = ToolResultMessage(tool_results=tool_results)
            new_messages.append(tool_message)
            yield tool_message, new_story

        if not stop:
            break

    thread.add_messages(*new_messages, save=True, reload_messages=True)


# import json
# print(json.dumps(story.current, indent=2))

# print(json.dumps(updated_args, indent=2))


def make_prompt():
    story = Story.from_id("66de2dfa5286b9dc656291c1", env=env)
    story_state = f"{json.dumps(story.current, indent=2)}"

    content = f"""The state of the current story (ID {story.id}) is: 
    
    {story_state}

    ---
    
    """
    return content


async def interactive_chat():
    user_id = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    agent = get_default_agent()
    thread = Thread.from_name(
        name="my_test_story4",
        user_id=user_id,
        env=env, 
        create_if_missing=True
    )
    story = None
    
    while True:
        try:
            message_input = input("\033[93m\033[1m\nUser:\t\t")
            if message_input.lower() == 'escape':
                break
            print("\033[93m\033[1m")
            
            message_content, metadata, attachments = preprocess_message(message_input)

            user_message = UserMessage(
                content=message_content,
                metadata=metadata,
                attachments=attachments
            )

            if story:
                system_message = get_system_message(story.id)
            else:
                system_message = system_prompt

            async for message, new_story in async_prompt2(
                thread, 
                agent, 
                user_message,
                system_message=system_message
            ): 
                print(message)
                if new_story:
                    story = new_story
                    #print(json.dumps(story.current, indent=2))
    
        except KeyboardInterrupt:
            break



if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_chat()) 



