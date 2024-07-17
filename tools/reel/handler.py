import sys
sys.path.append("../..")
from io import BytesIO
from pydub import AudioSegment
from pydantic import BaseModel, Field
from openai import OpenAI
from typing import List, Optional, Literal
import requests
import instructor

import s3
import voice
import tool
import utils


client = instructor.from_openai(OpenAI())


class Character(BaseModel):
    name: str = Field(..., description="The name of the character")
    description: str = Field(..., description="A short description of the character")


def extract_characters(prompt: str):
    characters = client.chat.completions.create(
        model="gpt-4-turbo",
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
    return characters or []
    

def write_reel(
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
        music_type, music_description = str, "A short and concise 1-sentence description of the music for the reel, structured as a prompt. Use descriptive words to convey the mood and genre of the music."
    else:
        music_type, music_description = Optional[None], "Leave this blank since there is no music."
    
    class Reel(BaseModel):
        image_prompt: str = Field(..., description="A short and concise 1-sentence description of the visual content for the reel, structured as a prompt, focusing on visual elements and action, not plot or dialogue")
        music_prompt: music_type = Field(..., description=music_description)
        speaker: speaker_type = Field(..., description=speaker_description)
        speech: speech_type = Field(..., description=speech_description)

    system_prompt = f"""You are a critically acclaimed screenwriter who writes incredibly captivating and original short-length single-scene reels of less than 1 minute in length which regularly go viral on Instagram, TikTok, Netflix, and YouTube.
    
    Users will prompt you with a premise or synopsis for a reel, as well as optionally a cast of characters, including their names and biographies.
    
    You will then write a script for a reel based on the information provided.
    
    Do not include an introduction or restatement of the prompt, just go straight into the reel itself."""

    reel = client.chat.completions.create(
        model="gpt-4-turbo",
        response_model=Reel,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
    )

    # override music prompt if provided by user
    if music and music_prompt:
        reel.music_prompt = music_prompt

    return reel
    

# modal.exception.InputCancellation
async def reel(args: dict):
    prompt = args.get("prompt")
    narrator = args.get("narrator")
    music = args.get("music")
    music_prompt = (args.get("music_prompt") or "").strip()
    min_duration = args.get("min_duration")
    width = args.get("width")
    height = args.get("height")
    
    characters = extract_characters(prompt)

    if narrator:
        characters.append(Character(name="narrator", description="The narrator of the reel is a voiceover artist who provides some narration for the reel"))
    
    voices = {
        c.name: voice.select_random_voice(c.description) 
        for c in characters
    }

    story = write_reel(prompt, characters, music, music_prompt)
    
    duration = min_duration

    print("characters", characters)
    print("voices", voices)
    print("story", story)

    speech_audio = None
    music_audio = None

    # generate speech
    if story.speech:
        speech_audio = voice.run(
            text=story.speech,
            voice_id=voices[story.speaker]
        )
        print("generated speech", story.speech)
        speech_audio = AudioSegment.from_file(BytesIO(speech_audio))
        silence1 = AudioSegment.silent(duration=2000)
        silence2 = AudioSegment.silent(duration=3000)
        speech_audio = silence1 + speech_audio + silence2
        duration = max(duration, len(speech_audio) / 1000)
    
    # generate music
    if music and story.music_prompt:
        audiocraft = tool.load_tool("tools/audiocraft")
        music = await audiocraft.async_run({
            "text_input": story.music_prompt,
            "model_name": "facebook/musicgen-large",
            "duration_seconds": int(duration)
        })
        print("generated music", story.music_prompt)
        music_bytes = requests.get(music[0]['files'][0]).content
        music_audio = AudioSegment.from_file(BytesIO(music_bytes))

    # mix audio
    audio = None
    if speech_audio and music:        
        audio = music_audio.overlay(speech_audio)        
    elif speech_audio:
        audio = speech_audio
    elif music:
        audio = music_audio

    txt2vid = tool.load_tool("../workflows/txt2vid")
    video = await txt2vid.async_run({
        "prompt": story.image_prompt,
        "n_frames": 128,
        "width": width,
        "height": height
    })
    output_url = video[0]
    print("txt2vid", output_url)

    if audio:
        buffer = BytesIO()
        audio.export(buffer, format="mp3")
        output = utils.combine_audio_video(buffer, output_url)
        output_url = s3.upload_file(output)

    print("output_url", output_url)

    return [output_url]
