import sys
sys.path.append("../..")
from io import BytesIO
from bson import ObjectId
from pydub import AudioSegment
from pydub.utils import ratio_to_db
from pydantic import BaseModel, Field
from openai import OpenAI
from typing import List, Optional, Literal
import requests
import instructor

import s3
import voice
import tool
import utils


import modal

import asyncio

from mongo import characters as mongo_characters


client = instructor.from_openai(OpenAI())


from pydantic.json_schema import SkipJsonSchema

class Character(BaseModel):
    name: str = Field(..., description="The name of the character")
    description: str = Field(..., description="A short description of the character")
    voice: SkipJsonSchema[Optional[str]] = Field(None, description="The voice id of the character") # todo: Literal[*voices]
    lora: SkipJsonSchema[Optional[str]] = Field(None, description="an alternqtive description of the character written in caps")


def extract_characters(
    prompt: str, 
    user: str = None,
    search_db: bool = True
):
    # first extract a list of characters from the prompt
    characters = client.chat.completions.create(
        model="gpt-3.5-turbo",
        response_model=Optional[List[Character]],
        messages=[
            {
                "role": "system",
                "content": "Extract and resolve a list of characters/actors/people from the following story premise. Do not include inanimate objects, places, or concepts. Only named or nameable characters.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    # search for characters in the database to get supporting info
    for character in characters:
        if not search_db:
            continue

        # first look for the user's characters with the same name
        fc = mongo_characters.find_one({
            "name": {"$regex": character.name, "$options": "i"},
            "user": ObjectId(user)
        }) if user else None

        # if no user-owned characters with same name, expand search to all characters
        if not fc:
            fc = mongo_characters.find_one({
                "name": {"$regex": character.name, "$options": "i"},
            })
            
        # if still no user-owned characters with same name, just return characters as-is
        if not fc:
            continue

        # replace character name and description with found character
        character.name = fc.get("name")
        character.description = fc.get("description")
        character.voice = fc.get("voice")

    return characters or []
    

def write_story(
    prompt: str, 
    characters: List[Character],
    music: bool,
    music_prompt: str
):
    if characters:
        names = [c.name for c in characters]
        speaker_type, speaker_description = Literal[*names], "Name of the speaker, if any voiceover."
        speech_type, speech_description = str, "If there is a voiceover, the text of the speech."
    else:
        speaker_type, speaker_description = Optional[None], "Leave this blank since there are no speakers."
        speech_type, speech_description = Optional[None], "Leave this blank since there are no speakers."

    if music:
        music_type, music_description = str, "A short and concise 1-sentence description of the music for the story, structured as a prompt. Use descriptive words to convey the mood and genre of the music."
    else:
        music_type, music_description = Optional[None], "Leave this blank since there is no music."
    
    class StoryClip(BaseModel):
        image_prompt: str = Field(..., description="A short and concise 1-sentence description of the visual content for the story clip, structured as a prompt, focusing on visual elements and action, not plot or dialogue")
        speaker: speaker_type = Field(..., description=speaker_description)
        speech: speech_type = Field(..., description=speech_description)

    class Story(BaseModel):
        clips: List[StoryClip] = Field(..., description="A sequence of clips that make up the story")
        music_prompt: music_type = Field(..., description=music_description)

    system_prompt = f"""You are a critically acclaimed screenwriter who writes incredibly captivating and original multiple-scene short films of 1-3 minutes in length which regularly go viral on Instagram, TikTok, Netflix, and YouTube.
    
    Users will prompt you with a premise or synopsis for a story, as well as optionally a cast of characters, including their names and biographies.
    
    You will then write a script for a story based on the information provided.
    
    Do not include an introduction or restatement of the prompt, just go straight into the story itself."""

    story = client.chat.completions.create(
        model="gpt-4-turbo",
        response_model=Story,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
    )

    # override music prompt if provided by user
    if music and music_prompt:
        story.music_prompt = music_prompt

    return story
    

async def story(
    args: dict, 
    user: str = None
):
    prompt = args.get("prompt")
    narrator = args.get("narrator")
    music = args.get("music")
    music_prompt = (args.get("music_prompt") or "").strip()
    min_duration = args.get("min_duration")
    width = args.get("width")
    height = args.get("height")
    speech_boost = 5
    
    characters = extract_characters(prompt, user)

    if narrator:
        characters.append(Character(name="narrator", description="The narrator of the story is a voiceover artist who provides some narration for the story"))
    
    print("characters", characters)

    voices = {
        c.name: c.voice or voice.select_random_voice(c.description) 
        for c in characters
    }

    print("THE VOICES!!!!")
    print(voices)

    story = write_story(prompt, characters, music, music_prompt)

    print("story", story)
    
    duration = min_duration

    print("characters", characters)
    print("voices", voices)
    print("story", story)

    metadata = {
        "story": story.model_dump(),
        "characters": [c.model_dump() for c in characters],
    }

    speech_audio = None
    music_audio = None

    for clip in story.clips[0:1]:
        print("clip", clip)

        # if clip.speech:
        #     speech_audio = voice.run(
        #         text=clip.speech,
        #         voice_id=voices[clip.speaker]
        #     )
        #     print("generated speech", clip.speech)
        #     speech_audio = AudioSegment.from_file(BytesIO(speech_audio))
        #     silence1 = AudioSegment.silent(duration=500)
        #     silence2 = AudioSegment.silent(duration=500)
        #     speech_audio = silence1 + speech_audio + silence2
        #     duration = max(duration, len(speech_audio) / 1000)
        #     # metadata["speech"] = s3.upload_audio_segment(speech_audio)


        #     txt2vid = tool.load_tool("../workflows/txt2vid")
        #     video = await txt2vid.async_run({
        #         "prompt": story.image_prompt,
        #         "n_frames": 128,
        #         "width": width,
        #         "height": height
        #     })
        #     output_url = video[0]
        #     print("txt2vid", output_url)