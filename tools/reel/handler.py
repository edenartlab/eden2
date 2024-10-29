import sys
sys.path.append("../..")

# sys.path.append("../../..")
from tools.media_utils.video_concat.handler import video_concat


import math
import asyncio
from io import BytesIO
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
import eden_utils


print("HI!")


print("HI2!")



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
    

async def reel(args: dict, user: str = None, env: str = None):
    print("OS TJOS MY REL")
    try:
    # if 1:

        print("RUN A REEL!!!")

        prompt = args.get("prompt")
        narrator = args.get("narrator")
        music = args.get("music")
        music_prompt = (args.get("music_prompt") or "").strip()
        min_duration = args.get("min_duration")
        
        orientation = args.get("orientation")
        if orientation == "landscape":
            width = 1280
            height = 768
        else:
            width = 768
            height = 1280

        
        speech_boost = 5

        if not min_duration:
            raise Exception("min_duration is required")

        print("ALL ARGS ARE", args)
        
        characters = extract_characters(prompt)

        if narrator:
            characters.append(Character(name="narrator", description="The narrator of the reel is a voiceover artist who provides some narration for the reel"))
        
        print("characters :: ", characters)

        voices = {
            c.name: voice.select_random_voice(c.description) 
            for c in characters
        }

        story = write_reel(prompt, characters, music, music_prompt)

        print("story", story)
        
        duration = min_duration

        print("characters", characters)
        print("voices", voices)
        print("story", story)

        metadata = {
            "reel": story.model_dump(),
            "characters": [c.model_dump() for c in characters],
        }

        print("metadata", metadata)

        speech_audio = None
        music_audio = None
        print("NEXT")
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
            metadata["speech"], _ = s3.upload_audio_segment(speech_audio)
            
        # generate music
        if music and story.music_prompt:
            musicgen = tool.load_tool("tools/musicgen")
            music = await musicgen.async_run({
                "prompt": story.music_prompt,
                "duration": int(duration)
            })
            print("THE MUSIC IS DONE!")
            print(music)
            print("generated music", story.music_prompt)
            music_bytes = requests.get(music[0]['url']).content
            music_audio = AudioSegment.from_file(BytesIO(music_bytes))
            metadata["music"], _ = s3.upload_audio_segment(music_audio)

        # mix audio
        audio = None
        if speech_audio and music_audio:
            diff_db = ratio_to_db(speech_audio.rms / music_audio.rms)
            music_audio = music_audio + diff_db
            speech_audio = speech_audio + speech_boost
            audio = music_audio.overlay(speech_audio)        
        elif speech_audio:
            audio = speech_audio
        elif music_audio:
            audio = music_audio
        
        print("THE AUDIO IS DONE!")
        print(audio)




        print("MAKE THE VIDEO!")
        
        flux_args = {
            "prompt": story.image_prompt,
            "width": width,
            "height": height
        }        
        print("flux_args", flux_args)
        use_lora = args.get("use_lora", False)
        if use_lora:
            lora = args.get("lora")
            lora_strength = args.get("lora_strength")
            flux_args.update({
                "use_lora": True,
                "lora": lora,
                "lora_strength": lora_strength
            })

        print("flux_args", flux_args)


        num_clips = int(duration // 10)
        print("num_clips", num_clips)
        txt2img = tool.load_tool("../workflows/workspaces/flux/workflows/flux_dev")
        images = []
        for i in range(num_clips):
            print("i", i)
            image = await txt2img.async_run(flux_args)
            print("THE IMAGE IS DONE!")
            print(image)
            output_url = image[0]["url"]
            images.append(output_url)

        runway = tool.load_tool("tools/runway")

        videos = []
        dur = 10
        for i in range(num_clips):
            if i == num_clips - 1 and duration % 10 < 5:
                dur = 5
            video = await runway.async_run({
                "prompt_image": images[i],
                "prompt_text": story.image_prompt,
                "duration": str(dur),
                "ratio": "16:9" if orientation == "landscape" else "9:16"
            })
            videos.append(video[0])

        print("videos", videos)

        # download videos
        # videos = [eden_utils.get_file_handler(".mp4", v) for v in videos]

        video = await video_concat({"videos": videos}, env=env)
        print("video", video)
        video = video[0]


        # txt2vid = tool.load_tool("../workflows/workspaces/video/workflows/txt2vid")
        # video = await txt2vid.async_run({
        #     "prompt": story.image_prompt,
        #     "n_frames": 128,
        #     "width": width,
        #     "height": height
        # })
        print("THE VIDEO IS DONE!")
        print(video)
        # output_url = video[0]["url"]
        # video = "output.mp4"

        # print("txt2vid", output_url)

        if audio:
            buffer = BytesIO()
            audio.export(buffer, format="mp3")
            output = eden_utils.make_audiovideo_clip(video, buffer)
            output_url, _ = s3.upload_file(output)

        print("output_url", output_url)
        print("metadata", metadata)

        return [output_url]


    except asyncio.CancelledError as e:
        print("asyncio CancelledError")
        print(e)
    except Exception as e:
        print("normal error")
        print(e)
        
