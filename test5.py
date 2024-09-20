import sys
from io import BytesIO
from pydub import AudioSegment
from pydub.utils import ratio_to_db
from pydantic import BaseModel, Field
from openai import OpenAI
from typing import List, Optional, Literal
import requests
import random
import instructor

import s3
import voice
import tool
import utils

from eden.client import EdenClient

from pydantic import BaseModel, Field, ConfigDict
from pydantic.json_schema import SkipJsonSchema
from anthropic import Anthropic
from openai import OpenAI
import instructor

client = EdenClient(stage=True)

import random
ridx = random.randint(0, 1000)

"""
- Write script
- Generate aesthetic + stills
- Animate stills, voiceover
- Music, concat

"""

provider = "openai"


def llm(
    system_message: str, 
    prompt: str, 
    response_model: BaseModel, 
    provider: Literal["anthropic", "openai"]
):
    # print("LLM", system_message)
    # print(prompt)

    if provider == "anthropic":
        claude = instructor.from_anthropic(Anthropic())
        result = claude.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=25000,
            max_retries=2,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            system=system_message,
            response_model=response_model,
        )
    elif provider == "openai":
        gpt = instructor.from_openai(OpenAI())
        result = gpt.chat.completions.create(
            model="gpt-4-turbo",
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
        )
    return result


genres = [
    "Action", "Adventure", "Comedy", "Drama", "Horror", "Science Fiction", 
    "Fantasy", "Thriller", "Mystery", "Romance", "Western", "Historical Fiction", 
    "Biography (Biopic)", "Documentary", "Musical", "Animation", "Family", 
    "Crime", "Noir", "War", "Epic", "Sports", "Superhero", "Post-Apocalyptic", 
    "Dystopian", "Spy", "Martial Arts", "Film Noir", "Cyberpunk", "Steampunk", 
    "Zombie", "Slasher", "Psychological Horror", "Body Horror", "Gothic", 
    "Paranormal", "Mockumentary", "Coming-of-Age", "Road Movie", "Buddy Comedy", 
    "Romantic Comedy", "Dark Comedy", "Satire", "Parody", "Black Comedy", 
    "Melodrama", "Political Drama", "Courtroom Drama", "Social Drama", "Period Piece", 
    "Historical Epic", "Swashbuckler", "Heist", "Gangster", "Detective", "Neo-Noir", 
    "Erotic Thriller", "Survival", "Disaster", "Space Opera", "Alien Invasion", 
    "Time Travel", "Techno-Thriller", "Psychological Thriller", "Legal Thriller", 
    "Conspiracy Thriller", "Revenge Thriller", "Religious", "Mythological", 
    "Sword and Sorcery", "Fairy Tale", "Urban Fantasy", "High Fantasy", "Low Fantasy", 
    "Grimdark", "Sword and Sandal", "Historical Romance", "Caper", "Art Film", 
    "Avant-Garde", "Experimental", "Absurdist", "Metafiction", "Magical Realism", 
    "Surrealist", "Folk Horror", "Eco-Horror", "Splatter", "Exploitation", 
    "Blaxploitation", "Spaghetti Western", "Samurai", "Kaiju", 
    "Mecha", "Jidaigeki", "Chanbara", "Tokusatsu", "Yakuza", "Giallo", 
    "Psychotronic", "Pulp", "Grindhouse", "Vigilante", "Stoner Comedy", 
    "Teen Comedy", "Gross-Out Comedy", "Screwball Comedy", "Slapstick", 
    "Romantic Fantasy", "Dieselpunk", "Retrofuturism", "Afrofuturism", "Climate Fiction", 
    "Anthology", "Docudrama", "Docufiction", "Music Documentary", "Rockumentary", 
    "Concert Film", "Road Comedy", "Space Western", "Biopunk", "Hard Sci-Fi", 
    "Soft Sci-Fi", "Speculative Fiction", "Alternate History", "Parallel Universe", 
    "Wuxia", "B-Movie", "Cult Film", "Midnight Movie", "Exploitation Horror", 
    "Mumblecore", "Southern Gothic", "Tropical Gothic", "Tech-Noir", "Weird Fiction", 
    "Weird Western", "Ghost Story", "Haunted House", "Found Footage", "Monster Movie", 
    "Creature Feature", "Kaiju (Giant Monster)", "Beach Party", "Troma Film", 
    "Lynchian", "Spiritual Film", "Christmas Film"
]

story_examples = [
    {
        "synopsis": "In 18th century Vienna, a talented but impoverished female composer disguises herself as a man to enter the prestigious music academy, navigating treacherous rivalries and forbidden romance while struggling to maintain her secret identity and create her masterpiece that could change the course of classical music forever.",
        "visual_aesthetic": "Opulent Rococo style, soft pastel color palette, candlelit interiors, powdered wigs, ornate costumes, gilded musical instruments, baroque architecture, misty Vienna streets"
    },
    {
        "synopsis": "In medieval Japan, a dishonored samurai seeks redemption by protecting a village from a band of ruthless warlords, uncovering a conspiracy that could change the course of history",
        "visual_aesthetic": "Traditional Japanese aesthetic, sumi-e ink wash technique, moody, muted earthy colors",
    },
    {
        "synopsis": "A documentary traces the enduring cultural, economic, and technological legacies of the ancient Silk Road, exploring how this network of trade routes disseminated ideas, beliefs, and technologies that shaped the civilizations of Europe, Asia, and the Middle East.",
        "visual_aesthetic": "Photorealistic, high contrast, cinematic, panoramic, 35mm film grain, Mediterannean",
    },
    {
        "synopsis": "In a dystopian future where memories can be bought and sold, a young rebel seeks to dismantle the corporation controlling these transactions, only to discover that her memory is being covertly manipulated by the very corporation she seeks to undermine.",
        "visual_aesthetic": "Dark, gritty, cyberpunk, concrete jungle, sketchy, matte anime feel", 
    },
]

class Story(BaseModel):
    synopsis: str = Field(
        ..., 
        description="A concise description of the plot, focusing on the main action, setting, and characters involved. What is this story about, what happens?"
    )
    visual_aesthetic: str = Field(
        ..., 
        description="A short sentence consisting of phrases that describe the aesthetic or visual characteristics, including but not limited to medium, genre, lighting, illustration technique, color pallette, mood, and other visual elements. **Do not** include and people or descriptions reminding one of people, nor any plot elements, or sound design. Just focus on visual characteristics."
    )
    model_config = ConfigDict(json_schema_extra={"examples": story_examples})


genre = random.choice(genres)

prompt = f"Write an idea for a story whose genre is {genre}. The synopsis should be descriptive and focus on plot elements, while the visual aesthetic is meant to be given to an illustrator or animator to guide the aesthetic design and specific visual elements that characterize the story."

story = llm(
    system_message="You are a critically acclaimed filmmaker who conceives ideas for films.",
    prompt=prompt,
    response_model=Story,
    provider=provider
)


character_examples = [
    {
        "name": "Seraphina Windrider",
        "description": "Seraphina is a young, enigmatic sorceress with a mysterious past. She was raised in secrecy by an ancient order of mages, and possesses immense magical potential, but her powers are unpredictable and uncontrollable. Driven by a deep sense of justice and a desire to find her place in a world fraught with conflict, Seraphina joins forces with Macklin to search for the legendary sword that once belonged to her father. Her journey is not just about retrieving the sword, but also about discovering her own origins and the true extent of her powers.",
        "appearance": "Seraphina is a woman with long, braided silver hair adorned with small charms, violet eyes, and wearing a deep blue robe with silver runes, knee-high leather boots, and an ancient amulet around her neck"
    },
    {
        "name": "Rico Alvarez",
        "description": "Rico 'Shade' Alvarez is a passionate graffiti artist from New York City, known for his large-scale murals that blend social commentary with vibrant, abstract designs. Raised in the Bronx, Rico uses his art to express the struggles and hopes of his community. Despite facing legal challenges and the ever-present threat of his work being erased, he remains fiercely dedicated to his craft, believing that street art is a powerful voice for the voiceless.",
        "appearance": "Rico is a lean, athletic man with a buzz cut, wearing a paint-splattered hoodie, ripped jeans, and a bandana around his neck, carrying a red backpack and holding a spray can."
    }
]

class Character(BaseModel):
    name: str = Field(..., description="The name of the character")
    description: str = Field(..., description="A description of the character, focusing on their personality traits, backstory, and their relationship to the plot and other characters.")
    appearance: str = Field(..., description="A single sentence describing exactly how the character looks, to be used by the set designer/cinematographer. Make sure to restate the character's name in the appearance, avoid pronouns.")
    voice: SkipJsonSchema[Optional[str]] = Field(None, description="The voice id of the character") # todo: Literal[*voices]
    # lora: SkipJsonSchema[Optional[str]] = Field(None, description="an alternqtive description of the character written in caps")

    model_config = ConfigDict(json_schema_extra={"examples": character_examples})

class Screenplay(BaseModel):
    characters: List[Character] = Field(
        ..., 
        description="A list of characters in the story, each with a name, description, and description of their appearance."
    )
    scenes: List[str] = Field(
        ..., 
        description="A list of scenes which tell the story from beginning to end, focusing on the main action, setting, and characters involved. Each scene should be a single sentence or short paragraph."
    )

system_message = f"You are a critically acclaimed screenwriter who writes incredibly captivating and original screenplays for films that are given to you by a producer."

prompt = f"""Write a detailed screenplay for the following story:

Synopsis: {story.synopsis}
Visual Aesthetic: {story.visual_aesthetic}

Write a cast of main characters and 6-8 scenes for this story."""

screenplay = llm(
    system_message=system_message,
    prompt=prompt,
    response_model=Screenplay,
    provider=provider
)

# assign voices to characters
narrator = True
if narrator:
    screenplay.characters.append(Character(name="Narrator", description="The narrator of the story is a voiceover artist who provides some narration for the story", appearance="None"))

voices = {
    c.name: voice.select_random_voice(c.description) 
    for c in screenplay.characters
}


class StoryboardFrame(BaseModel):
    image: str = Field(
        ..., 
        description="A sentence which captures the main action of a scene description, structured as a text-to-image prompt precisely describing a single event in the scene. Do not restate or include any contextual or non-visual information, and do not include surrounding details. Simply describe in plain language what is happening. The image will go to an illustrator to draw. The illustrator does not need to know anything else about the story."
    )
    dialogue: Optional[str] = Field(
        ..., 
        description="You may optionally include some lines of dialogue to be spoken by a character involved in the scene, or from the narrator if there is one. Some scenes may be silent."
    )
    dialogue_speaker: Optional[str] = Field(
        ..., 
        description="If and ony if there is dialogue, then state the name of the character who is speaking the dialogue."
    )


storyboard_examples = [
    {
        "frames": [
            {
                "image": "A man with sunglasses in a suit is walking down a street, looking tense, being followed by a woman on a bicycle",
                "dialogue": None,
                "dialogue_speaker": None
            },
            {
                "image": "A woman in a white lab coat sits at a workstation looking at 5 computer screens, looking worried",
                "dialogue": "We need to shut it down, Smith. There's no other way for us to preserve the elixir. You remember what the oracle told us. If we don't, we're done here.",
                "dialogue_speaker": "Dr. Jane Stewart"
            },
            {
                "image": "A computer screen in a laboratory displays a 3D rendering of a molecule, next to a video phone window with a man in a suit and sunglasses.",
                "dialogue": "I'm sorry, but I can't let you do that, Doctor. As you know, it's against the ordinances set forth by the council. You have 24 hours. Use them wisely.",
                "dialogue_speaker": "Agent Smith"
            },
        ],
        "music_prompt": "A slow, ominous piano melody with a dark, suspenseful atmosphere, intermittent percussive elements, tension building."
    }
]

class Storyboard(BaseModel):
    frames: List[StoryboardFrame] = Field(
        ..., 
        description="A list of scenes which tell the story from beginning to end, focusing on the main action, setting, and characters involved. Each scene should be a single sentence or short paragraph."
    )
    music_prompt: str = Field(
        ..., 
        description="A prompt for a music composer to create a song for the story."
    )

    model_config = ConfigDict(json_schema_extra={"examples": storyboard_examples})

system_message = "You are a critically acclaimed storyboard artist who takes screenplays and designs storyboard for them."

# character_str = ""
# for character in screenplay.characters:
#     character_str += f"{character.name}: {character.description}\n"

character_summary = "\n\n".join([f"Name: {character.name}\nDescription: {character.description}" for character in screenplay.characters])
scenes_summary = "\n\n".join([f"{i+1}. {scene}" for i, scene in enumerate(screenplay.scenes)])

prompt = f"""You have been given the following screenplay:

---
## Synopsis

{story.synopsis}

## Visual Aesthetic

{story.visual_aesthetic}

## Characters 

{character_summary}

## Scenes

{scenes_summary}

---

Create a list of storyboard frames corresponding to the scenes in the same order. There should usually be 1 frame per scene, but you can have 2 frames for a scene if the action is complex.

Each frame contains the following things:
- An image prompt, which simply describes what is happening in the frame, referencing the characters (if any) and action. Do not include dialogue, aesthetic details, or adjectives. This should be very plain and literal.
- An optional dialogue line, which is spoken by a character, or by a narrator if there is one. If there is nothing spoken here, leave this blank. Aim for around 5-8 seconds of dialogue (around 25-50 words).
- The name of the character speaking the dialogue, if there is dialogue. If dialogue is blank, leave this also blank. If dialogue is not blank, then this must precisely match the FULL NAME of one of the characters listed in the screenplay, or "Narrator".

Lastly, in addition to the frame list, write a prompt for a single musical composition that will serve as the background soundtrack for the entire film. The prompt should be densely packed with details about the music, including instruments, mood, tempo, and any other details that a composer would need to know."""

storyboard = llm(
    system_message=system_message,
    prompt=prompt,
    response_model=Storyboard,
    provider=provider
)



print(story.model_dump_json(indent=2))
print("----")
print(screenplay.model_dump_json(indent=2))
print("----")
print(storyboard.model_dump_json(indent=2))



import asyncio
#asyncio.run(main())


from tool import load_tool

txt2img = load_tool("../workflows/workspaces/img_tools/workflows/txt2img")
img2vid = load_tool("../workflows/workspaces/video/workflows/animate_3D")
flux = load_tool("../workflows/workspaces/flux/workflows/flux")

# result = client.create("flux", {
#     "prompt": story.visual_aesthetic,
#     "width": 1344, "height": 768
# })
result = flux.run({
    "prompt": story.visual_aesthetic,
    "width": 1344, "height": 768
})
print(result)
style_image = result[0]["url"]

clips = []
audio_clips = []
video_clips = []

total_duration = 0
video_files = []
for f, frame in enumerate(storyboard.frames):
    # print(frame.image)
    # result = client.create("txt2img", {
    #     "prompt": frame.image,
    #     "use_ipadapter": True,
    #     "style_image": style_image,
    #     "ipadapter_strength": 0.5,
    #     "width": 1344, "height": 768
    # })
    # clips.append(result[0]["url"])
    result = txt2img.run({
        "prompt": frame.image,
        "use_ipadapter": True,
        "style_image": style_image,
        "ipadapter_strength": 0.5,
        "width": 1344, "height": 768
    })
    clips.append(result[0]["url"])
    result = result[0]["url"]
    # result = clips[f]
    duration = 6
    audio = None
    if frame.dialogue:
        print(frame.dialogue_speaker, "::", voices.get(frame.dialogue_speaker), "::", frame.dialogue)
        # generate speech
        voice_id = voices.get(frame.dialogue_speaker, voice.select_random_voice())
        speech_audio = voice.run(
            text=frame.dialogue,
            voice_id=voice_id
        )
        audio_clips.append(speech_audio)
        # speech_audio = audio_clips[f]
        speech_audio = AudioSegment.from_file(BytesIO(speech_audio))
        speech_duration = len(speech_audio) / 1000
        
        # 3, 2.5, 0.8, 1.7, 5.5
        # 5, 1.5, 0.45, 1.05

        extra_silence = max(0, 8 - speech_duration) / 2
        silence1_duration = min(extra_silence * 0.3, 0.5)
        silence2_duration = extra_silence - silence1_duration

        silence1 = AudioSegment.silent(duration=int(1000*silence1_duration))
        silence2 = AudioSegment.silent(duration=int(1000*silence2_duration))
        speech_audio = silence1 + speech_audio + silence2
        duration = len(speech_audio) / 1000
        print("duration", duration)
        audio = speech_audio
    else:
        audio_clips.append(None)
        print("none")
    
    if duration * 8 > 64:
        n_frames = 64
        loop = True
    else:
        n_frames = int(duration * 8)
        loop = False    
    # result2 = client.create("animate_3D", {
    #     "image": result,
    #     "n_frames": n_frames,
    #     "loop": loop,
    # })
    result2 = img2vid.run({
        "image": result,
        "n_frames": n_frames,
        "loop": loop,
    })
    video_clips.append(result2[0]["url"])
    output_url = result2[0]["url"]
    # output_url = video_clips[f]
    if audio:
        buffer = BytesIO()
        audio.export(buffer, format="mp3")
        output = utils.combine_audio_video(buffer, output_url)
        video_files.append(output)
    else:
        clip_filename = f"__theclip_{ridx}_{f}.mp4"
        response2 = requests.get(output_url)
        response2.raise_for_status()
        # download to temp file
        with open(clip_filename, "wb") as f:
            f.write(response2.content)
        video_files.append(clip_filename)
        # output_url, _ = s3.upload_file(output, env="STAGE")
        # print("output_url", output_url)
    total_duration += duration


print("ALL THJE VIDEO CLIPS", video_files)

utils.concatenate_videos(video_files, f"themovie_{ridx}.mp4")

import tempfile

print("total_duration", total_duration)
from tool import load_tool
audiocraft = load_tool("tools/audiocraft")

music = audiocraft.run({
    "text_input": storyboard.music_prompt,
    "duration_seconds": total_duration,
    "model_name": "facebook/musicgen-large"
})

print(music)


response = requests.get(music[0]["url"])
response.raise_for_status()
music_audio = AudioSegment.from_file(BytesIO(response.content))
music_audio -= 15

# save to tgemp file
music_audio.export(f"music1_{ridx}.mp3", format="mp3")

audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
print("audio_file", audio_file)
audio_file.write(response.content)
audio_file.flush()







utils.mix_video_audio(
    f"themovie_{ridx}.mp4",
    f"music1_{ridx}.mp3", #audio_file.name,
    f"themovie2_{ridx}.mp4",
)
with open(f"themovie2_{ridx}.mp4", "rb") as f:
    video_bytes = f.read()








# style_image = result[0]["url"]
# # style_image = "https://dtut5r9j4w7j4.cloudfront.net/7c69136760272ab7106f21c96822d8897e5d6bfadede7ac2460d066cf9f1f47d.png"
# # style_image = "https://dtut5r9j4w7j4.cloudfront.net/2143c39b0552253376cc6a87ba08e12e6ffe7634e061c9251f0d826c2397d723.png"

# print("STYLE IMAGE", style_image)
# print("=====")
# for scene in scenes.scene_prompts:
#     prompt = f"{scene}. Style: {scenes.illustration_instructions}"
#     result = client.create("txt2img", {
#         "prompt": prompt,
#         "use_ipadapter": True,
#         "style_image": style_image,
#         "ipadapter_strength": 0.5,
#         "width": 1344, "height": 768
#     })
#     print(result)




#     # except asyncio.CancelledError as e:
#     #     print("asyncio CancelledError")
#     #     print(e)
#     # except Exception as e:
#     #     print("normal error")
#     #     print(e)
        
