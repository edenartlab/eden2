from eden import EdenClient

eden_client = EdenClient()

thread_id = eden_client.get_or_create_thread("test_thread_anthro")
print(thread_id)

response = eden_client.chat(
    thread_id=thread_id, 
    message={
        "content": "make a picture of a dog with a dark grittier style",  
        "settings": {}, 
        "attachments": []
    }
)

print(response)

