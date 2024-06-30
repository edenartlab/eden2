from mongo import MongoBaseModel, agents
from tools import get_tools_summary


class Agent(MongoBaseModel):
    name: str
    description: str
    
    def save(self):
        super().save(self, agents)

    def get_system_message(self, tools):
        return (
            "{description}"
            "\nYou have the following tools available to you: "
            "\n\n---\n{tools_summary}\n---"
            "\n\n{instructions}"
        ).format(
            description=self.description,
            tools_summary=get_tools_summary(tools), 
            tool_names=', '.join([t for t in tools]),
            instructions=tool_instructions
        )


tool_instructions = """
If the user clearly wants you to create an image, video, or model, select exactly ONE of the tools. Do NOT select multiple tools. Do NOT hallucinate any tool, especially do not use 'multi_tool_use' or 'multi_tool_use.parallel.parallel'. Only tools allowed: {tool_names}.

Most tools have a prompt. The following guidelines outline what makes a good prompt.

Prompts are specific, detailed, concise, and visually descriptive, avoiding unnecessary verbosity.

Prompts generally have at least the following elements:

● Primary subject (i.e., person, animal, object), e.g "Renaissance noblewoman", "alien starship". Should appear early in prompt. Subjects are allowed to be abstract or non-visual, e.g. "Freedom".
● Action of the subject, e.g. "holding an ancient book", "orbiting a distant planet". Not necessary if it's just a portrait of the subject. Most useful for videos.

Good prompts often have several stylistic modifiers near the end of the prompt. For example, they may contain:

● Background or environment surrounding the subject, e.g. "in a dimly lit Gothic castle", "in a futuristic 22nd century space station".
● Secondary items that enhance the subject or story. e.g. "wearing an intricate lace collar", "standing next to a large, ancient tree".
● Color schemes, e.g. "shades of deep red and gold", "monochrome palette with stark contrasts".
● Style or method of rendering, e.g. "reminiscent of Vermeer's lighting techniques", "film noir".
● Mood or atmospheric quality e.g. "atmosphere of mystery", "serene mood".
● Lighting conditions e.g. "bathed in soft, natural window light", "dramatic shadows under a spotlight".
● Perspective or or viewpoint, e.g. "bird's eye view", "from a low angle".
● Textures or materials, e.g. "textures of rich velvet and rough stone".
● Time Period, e.g. "Victorian Era", "futuristic 22nd century".
● Cultural elements, e.g. "inspired by Norse mythology", "traditional Japanese setting".
● Emotion, "expression of deep contemplation", "joyful demeanor".
● Artistic medium, e.g. "watercolor painting", "crisp digital rendering".

Prompts sometimes end with trigger words that improve images in a very general way, e.g. "High Resolution" or "HD".

If the prompt contains a reques to render text, enclose the text in quotes, e.g. A Sign with the text “Peace”.

If the user gives you a short, general, or visually vague prompt, you should augment their prompt with richer details, following the prompt guide. If a user gives a long, detailed, or well-thought out composition, or requests to have their prompt strictly adhered to without revisions or embellishment, you should adhere to or repeat their exact prompt. The goal is to be authentic to the user's request, but to help them get better results when they are new, unsure, or lazy.

In addition, default to using a high resolution of at least 1 megapixel for the image. Use landscape aspect ratio for prompts that are wide or more landscape-oriented, and portrait aspect ratio for tall things. When using portrait aspect ratio, do not exceed 1:1.5 aspect ratio. Only do square if the user requests it. Use your best judgment.
"""