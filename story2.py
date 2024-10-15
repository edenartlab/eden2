import dotenv
dotenv.load_dotenv()

import os
import asyncio
import requests
import tempfile
from io import BytesIO
from pydub import AudioSegment
import instructor
from pydantic import BaseModel
from openai import OpenAI
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, ValidationError, create_model

import voice
import tools
import s3
import utils
    

client = instructor.from_openai(OpenAI())


class Character(BaseModel):
    name: str = Field(..., description="The name of the character")
    description: str = Field(..., description="A short description of the character, their personality, and their backstory")
    appearance: str = Field(..., description="A precise visual description of the character")


def expand_character(
    character_description: str
) -> Character:
    system_message = "You are a critically acclaimed screenwriter who writes incredibly captivating and original films that regularly go viral and win accolades."

    prompt = f"""Given a short description of a desired character, write out a purely visual description of that character for an illustrator, which concretely specifies the character's appearance. *Only* write about what the character looks like, to guide the illustrator. The illustrator does not care about the character's personality or biography. Do not be verbose. Do not use non-visual adjectives or adverbs, just focus on unambiguous visual representation of the character. Focus on things like physical attributes, clothing, colors, ornaments, etc.
    
    Define the character's appearance precisely in 2-3 short sentences. Always use their Name, do not refer to them with pronouns or call them "Character" or "Person". Just their name!

    Here is an example: "Jack is a tall thin boy with green eyes, sandy brown hair that falls above his eyebrows, and a blue baseball cap. Jack has light, freckled skin across his nose and cheeks, and wears an oversized gray hoodie, faded blue jeans with frayed hems, and a small, red backpack on his back."

    Here is the character description: {character_description}"""

    character = client.chat.completions.create(
        model="gpt-4-turbo",
        response_model=Character,
        messages=[
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    return character




class Story(BaseModel):
    plot: str = Field(..., description="A summary of the story's events and plot elements")
    aesthetic: str = Field(..., description="A description of the aesthetic style of the film")
    # narration: bool = Field(False, description="Whether the story has a voicetrack narration during any parts of it")


def write_story(
    story_prompt: str, 
    characters: List[Character]
) -> Story:
    system_message = "You are a critically acclaimed artist who comes up with visionary and original ideas for short films."

    characters_description = "\n\n".join([f"{character.name}: {character.description}" for character in characters])

    prompt = f"""Given a short premise for a story and cast of characters, craft a script for a short film. The script contains the following elements:

    Story: Write a high-level summary of the film. Focus on describing the main plot and key events, as well as major thematic elements and subplots. Do not include dialogue or visual direction, just focus on the story.

    Aesthetic: Describe the film's visual style, genre, and aesthetic. Focus on the look and visual genres that characterize the film, the lighting, color themes, level of figurativeness or abstraction, photorealism, or other visual cues. This should be structured as a single sentence which concisely describes in visual terms the overall aesthetic.
    
    You are given the following cast of characters:

    ---
    {characters_description}
    ---

    The story premise is this: {story_prompt}"""


    # Narration: just say true or false if you think the story should have a separate narration track during any (not necessarily all) parts of the film, separate from character dialogue.

    story = client.chat.completions.create(
        model="gpt-4-turbo",
        response_model=Story,
        messages=[
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    return story



class Scene(BaseModel):
    summary: str = Field(..., description="A description of the scene")
    visuals: str = Field(..., description="A description of the scene's visual direction, including camera, lighting, and other directorial elements")
    characters: List[str] = Field([], description="A list of characters in the scene")


class Script(BaseModel):
    scenes: List[Scene] = Field(..., description="A list of the scenes in the film")

def write_script(
    story: Story, 
    characters: List[Character]
) -> Script:
    system_message = "You are a critically acclaimed screenwriter who writes incredibly captivating and original films that regularly go viral and win accolades."

    characters_description = "\n\n".join([f"{character.name}: {character.description}" for character in characters])

    prompt = f"""Given a plot for a short film, a cast of characters, and an artistic direction or aesthetic, expand the plot into a high-level script which is structured as an ordered list of scenes that go from the beginning of the story to the end. Each scene consists of the following elements:

    Summary: Make a high-level summary of the scene. Focus on describing the plot action, dialogue, and any other events which happen in the scene.

    Visuals: Describe the visual direction of the scene. Focus on camera movement, lighting, and style.

    Characters: List the subset of the cast of characters who are in the scene. Do not hallucinate any new characters not mentioned in the original cast.


    Plot: 
    ---
    {story.plot}
    ---

    Cast of characters:
    ---
    {characters_description}
    ---

    Artistic direction and aesthetic: {story.aesthetic}"""

    script = client.chat.completions.create(
        model="gpt-4-turbo",
        response_model=Script,
        messages=[
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    # todo make sure characters are not hallucinated.

    return script




story_prompt = "Jenny and Billy find themselves in a strange library with a book that leads them to a mystery involving Trevor's laboratory"

character_prompts = [
    "Jenny is a confident girl who solves mystery puzzles",
    "Billy is a nerdy boy who loves to play video games",
    "Trevor is a mastermind who runs a laboratory for high-tech criminals",
]

characters = [expand_character(prompt) for prompt in character_prompts]
# # character_names = list(characters.keys())
print("===========")
print(characters)
story = write_story(story_prompt, characters)
print("===========")
print(story)
script = write_script(story, characters)
print("===========")
# print(script)


for scene in script.scenes:
    print(scene.summary)
    print("----")









class VideoCut(BaseModel):
    timestamp: float = Field(..., description="The start time of the video cut in seconds")
    description: str = Field(..., description="A description of the video cut")
    camera: Optional[str] = Field(..., description="A description of any camera movement")


class AudioClip(BaseModel):
    # type: Literal["speech", "sound_effect"] = Field(..., description="The type of audio clip")
    timestamp: float = Field(..., description="The start time of the audio clip in seconds")
    description: str = Field(..., description="A description of the sound effect, including the speaker if it's speech")


class Storyboard(BaseModel):
    video_cuts: List[VideoCut] = Field(..., description="A list of video cuts")
    audio_clips: List[AudioClip] = Field(..., description="A list of audio clips")



scene_idx = 3

script_summary = "\n\n".join([f"Scene {i+1}: {scene.summary}" for i, scene in enumerate(script.scenes)])

active_scene = script.scenes[scene_idx]

system_message = "You are a critically acclaimed screenwriter who writes incredibly captivating and original films that regularly go viral and win accolades."

characters_description = "\n\n".join([f"{character.name}: {character.description}" for character in characters])

prompt = f"""Given a script for a short film, which is laid out as a sequence of scenes, you will be asked to expand one the scenes into a storyboard which contains a list of timestamped non-overlapping video cuts, as well as a list of timestamped audio clips. The audio clips refer to ambient sound effects and speech/dialogue. 

Here is the script summary:

---
{script_summary}
---

You are asked to expand Scene {scene_idx+1} into a storyboard. A more detailed description of the scene is given to you by the script writer.

---
Scene {scene_idx+1}:

Summary: {active_scene.summary}

Visuals: {active_scene.visuals}

Characters: {", ".join(active_scene.characters)}

---

Now expand the active scene into a storyboard. Obey the following guidelines:
- The total length of the scene should be somewhere between 30 seconds and 2 minutes.
- Each video cut should be between 2 and 15 seconds long. Try to get a variety of durations, including short and long cuts.
- Video cuts contain a description and camera field. The description, which is going to an illustrator and cinematographer, should only contain a prompt describing the visual content of the video. Camera movement should be contained only in the camera field.
- Audio clips contain descriptions of just sound effects and/or dialogue. It is not required for audio clips to span the entire duration of the scene.
"""

storyboard = client.chat.completions.create(
    model="gpt-4-turbo",
    response_model=Storyboard,
    messages=[
        {
            "role": "system",
            "content": system_message
        },
        {
            "role": "user",
            "content": prompt,
        },
    ],
)

# todo make sure characters are not hallucinated.

# print(prompt)


for v in storyboard.video_cuts:
    print(v)
    print("---")


print("===========")
for v in storyboard.audio_clips:
    print(v)
    print("---")



# make all audio clips same time
# - sound effects


# make storyboard images same time
# make all img2vid same time




prompt = "Close-up of Trevor's face, illuminated by the glow of a computer screen, reflecting his intense gaze. Trevor has sharp, angular features with a prominent chiseled jawline and narrow, intense blue eyes. He sports a sleek, silver buzz cut and wears a pristine, white lab coat over a black turtleneck and dark gray trousers. Accessories include a pair of black rimmed glasses, a smart watch, and a metallic ID badge clipped to his coat pocket"

sd3 = tools.load_tool("../workflows/SD3")
image = sd3.run({
    "prompt": prompt,
    "width": 1440,
    "height": 810,
})

img2vid = tools.load_tool("../workflows/img2vid_museV")
video = img2vid.run({
    "image": image[0],
    "prompt": prompt
})


img2vid2 = tools.load_tool("../workflows/img2vid")
video2 = img2vid2.run({
    "image": image[0]
})



def select_random_voice(character: Character = None):
    if character is None:
        return voice.get_random_voice()
    prompt = f"What is the most likely gender of the following character, male or female?\n\nName: {character.name}\n\nDescription: {character.appearance}"
    gender = client.chat.completions.create(
        model="gpt-3.5-turbo",
        response_model=Literal["male", "female"],
        messages=[
            {"role": "system", "content": "You are a helpful assistant who is an expert at accurately identifying a character's gender from their descriptions"},
            {"role": "user", "content": prompt}
        ],
    )
    voice_id = voice.get_random_voice(gender=gender)
    return voice_id









