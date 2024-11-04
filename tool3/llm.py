

Thread
- time-sorted array of messages
- anthropic_assemble_messages, openai_assemble_messages




prepare_messages
- max(20 messages)

anthropic_assemble_messages |
openai_assemble_messages






anthropic_assemble_messages
---
start with first user_message, is_user = True




anthropic:

messages = [UserMessage()]

for each message sort by earliest

    if message.role == user:
        if messages[-1] != assistant:
            messages.append(message)
        latest_user_message.add(message)

    elif message.role == "assistant":
        user_message = message.reply_to
        messages.insert_after(user_message, message)
        
    elif message.role == "tool":
        assistant_message = message.reply_to
        messages.insert_after(assistant_message, message)

    
    # make sure all tool calls have tool_results after
        



openai:

messages = [UserMessage()]

for each message sort by earliest

    if message.role == "user":
        messages.append(message)
        
    elif message.role == "assistant":
        user_message = message.reply_to
        messages.insert_after(user_message, message)
        
    elif message.role == "tool":
        assistant_message = message.reply_to
        messages.insert_after(assistant_message, message)



        



user_message = UserMessage(
    role='user',
    user=ObjectId, (discord_user, twitter_user, etc)  ( -> this is name)
    attachments=Dict()
)



User (Clerk, Web3Auth):
    userId

Agent(MongoModel)
    auth_user:
    is_user: true|false
    has manna
    has profile
    has rate limits
    description: 
    instructions: 



    


Concepts(MongoVersionableModel)
    base_model:
    edits:
    original
    current


ChatMessage(MongoModel)
    role: Literal["user", "assistant", "system", "tool"]
    agent: AgentVersion

class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    (name is derived from super.agent) 
    content: str
    concepts: Optional[Dict[str, ConceptVersion]] = None
    attachments: Optional[List[str]] = None


class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]


class ToolResult(BaseModel):
    id: str
    name: str
    result: Optional[Any] = None
    error: Optional[str] = None

class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    (name is derived from super.agent) 
    content: Optional[str] = ""
    thought: Optional[str] = ""
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Tool calls")
    finish_reason?


class ToolResultMessage(ChatMessage):
    role: Literal["tool"] = "tool"
    tool_results: List[ToolResult]


Thread:
    auth_user:
    slug: 
    messages: List[ChatMessage]




think:
    receives a new user message
    observes, makes plan, makes intentions
    intentions:
        intentions: 
        chat: true|false

        