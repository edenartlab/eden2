from io import BytesIO
from pydub import AudioSegment
from pydantic import BaseModel, Field, ConfigDict
from pydantic.json_schema import SkipJsonSchema
from anthropic import Anthropic
from openai import OpenAI
from typing import List, Optional, Literal
import math
import requests
import random
import instructor

import voice
import utils
from tool import load_tool


import random
ridx = random.randint(0, 1000)

import asyncio
#asyncio.run(main())
from tool import load_tool

txt2img = load_tool("../workflows/workspaces/img_tools/workflows/txt2img")
img2vid = load_tool("../workflows/workspaces/video/workflows/animate_3D")
flux = load_tool("../workflows/workspaces/flux/workflows/flux")

default_model = "gpt-4-turbo"





def llm(
    system_message: str, 
    prompt: str, 
    response_model: BaseModel, 
    model: Literal["gpt-3.5-turbo", "gpt-4-turbo", "claude-3-5-sonnet-20240620"]
):
    # print("LLM", system_message)
    # print(prompt)
    provider = "openai" if model.startswith("gpt") else "anthropic"

    if provider == "anthropic":
        claude = instructor.from_anthropic(Anthropic())
        result = claude.messages.create(
            model=model,
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
            model=model,
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
        )
    return result


genres = [
    "Action", "Adventure", "Comedy", "Drama", "Horror", "Science Fiction", "Fantasy", "Thriller", "Mystery", "Romance", "Western", "Historical Fiction", "Biography (Biopic)", "Documentary", "Musical", "Animation", "Family", "Crime", "Noir", "War", "Epic", "Sports", "Superhero", "Post-Apocalyptic", "Dystopian", "Spy", "Martial Arts", "Film Noir", "Cyberpunk", "Steampunk", "Zombie", "Slasher", "Psychological Horror", "Body Horror", "Gothic", "Paranormal", "Mockumentary", "Coming-of-Age", "Road Movie", "Buddy Comedy", "Romantic Comedy", "Dark Comedy", "Satire", "Parody", "Black Comedy", "Melodrama", "Political Drama", "Courtroom Drama", "Social Drama", "Period Piece", "Historical Epic", "Swashbuckler", "Heist", "Gangster", "Detective", "Neo-Noir", "Erotic Thriller", "Survival", "Disaster", "Space Opera", "Alien Invasion", "Time Travel", "Techno-Thriller", "Psychological Thriller", "Legal Thriller", "Conspiracy Thriller", "Revenge Thriller", "Religious", "Mythological", "Sword and Sorcery", "Fairy Tale", "Urban Fantasy", "High Fantasy", "Low Fantasy", "Grimdark", "Sword and Sandal", "Historical Romance", "Caper", "Art Film", "Avant-Garde", "Experimental", "Absurdist", "Metafiction", "Magical Realism", "Surrealist", "Folk Horror", "Eco-Horror", "Splatter", "Exploitation", "Blaxploitation", "Spaghetti Western", "Samurai", "Kaiju", "Mecha", "Jidaigeki", "Chanbara", "Tokusatsu", "Yakuza", "Giallo", "Psychotronic", "Pulp", "Grindhouse", "Vigilante", "Stoner Comedy", "Teen Comedy", "Gross-Out Comedy", "Screwball Comedy", "Slapstick", "Romantic Fantasy", "Dieselpunk", "Retrofuturism", "Afrofuturism", "Climate Fiction", "Anthology", "Docudrama", "Docufiction", "Music Documentary", "Rockumentary", "Concert Film", "Road Comedy", "Space Western", "Biopunk", "Hard Sci-Fi", "Soft Sci-Fi", "Speculative Fiction", "Alternate History", "Parallel Universe", "Wuxia", "B-Movie", "Cult Film", "Midnight Movie", "Exploitation Horror", "Mumblecore", "Southern Gothic", "Tropical Gothic", "Tech-Noir", "Weird Fiction", "Weird Western", "Ghost Story", "Haunted House", "Found Footage", "Monster Movie", "Creature Feature", "Kaiju (Giant Monster)", "Beach Party", "Troma Film", "Lynchian", "Spiritual Film", "Christmas Film"
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
    model=default_model
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

# system_message = f"You are a critically acclaimed screenwriter who writes incredibly captivating and original screenplays for films that are given to you by a producer."

# prompt = f"""Write a detailed screenplay for the following story:

# Synopsis: {story.synopsis}
# Visual Aesthetic: {story.visual_aesthetic}

# Write a cast of main characters and 6-8 scenes for this story."""

# screenplay = llm(
#     system_message=system_message,
#     prompt=prompt,
#     response_model=Screenplay,
#     model=default_model
# )

# # assign voices to characters
# narrator = True
# if narrator:
#     screenplay.characters.append(Character(name="Narrator", description="The narrator of the story is a voiceover artist who provides some narration for the story", appearance="None"))

# voices = {
#     c.name: voice.select_random_voice(c.description) 
#     for c in screenplay.characters
# }


# class StoryboardFrame(BaseModel):
#     image: str = Field(
#         ..., 
#         description="A sentence which captures the main action of a scene description, structured as a text-to-image prompt precisely describing a single event in the scene. Do not restate or include any contextual or non-visual information, and do not include surrounding details. Simply describe in plain language what is happening. The image will go to an illustrator to draw. The illustrator does not need to know anything else about the story."
#     )
#     # dialogue: Optional[str] = Field(
#     #     ..., 
#     #     description="You may optionally include some lines of dialogue to be spoken by a character involved in the scene, or from the narrator if there is one. Some scenes may be silent."
#     # )
#     # dialogue_speaker: Optional[str] = Field(
#     #     ..., 
#     #     description="If and ony if there is dialogue, then state the name of the character who is speaking the dialogue. This must precisely match the name of a character"
#     # )
#     dialogue: str = Field(
#         ..., 
#         description="You may include some lines of dialogue to be spoken by a character involved in the scene, or from the narrator if there is one."
#     )
#     dialogue_speaker: str = Field(
#         ..., 
#         description="State the name of the character who is speaking the dialogue. This must precisely match the name of a character."
#     )

# storyboard_examples = [
#     {
#         "frames": [
#             {
#                 "image": "A man with sunglasses in a suit is walking down a street, looking tense, being followed by a woman on a bicycle",
#                 # "dialogue": None,
#                 # "dialogue_speaker": None
#                 "dialogue": "Officer Feinberg, do you copy? The target is moving towards the warehouse district.I am following behind him by bike.",
#                 "dialogue_speaker": "Kelsey"
#             },
#             {
#                 "image": "A woman in a white lab coat sits at a workstation looking at 5 computer screens, looking worried",
#                 "dialogue": "We need to shut it down, Smith. There's no other way for us to preserve the elixir. You remember what the oracle told us. If we don't, we're done here.",
#                 "dialogue_speaker": "Dr. Jane Stewart"
#             },
#             {
#                 "image": "A computer screen in a laboratory displays a 3D rendering of a molecule, next to a video phone window with a man in a suit and sunglasses.",
#                 "dialogue": "I'm sorry, but I can't let you do that, Doctor. As you know, it's against the ordinances set forth by the council. You have 24 hours. Use them wisely.",
#                 "dialogue_speaker": "Agent Smith"
#             },
#         ],
#         "music_prompt": "A slow, ominous piano melody with a dark, suspenseful atmosphere, intermittent percussive elements, tension building."
#     }
# ]

# class Storyboard(BaseModel):
#     frames: List[StoryboardFrame] = Field(
#         ..., 
#         description="A list of scenes which tell the story from beginning to end, focusing on the main action, setting, and characters involved. Each scene should be a single sentence or short paragraph."
#     )
#     music_prompt: str = Field(
#         ..., 
#         description="A prompt for a music composer to create a song for the story."
#     )

#     model_config = ConfigDict(json_schema_extra={"examples": storyboard_examples})

# system_message = "You are a critically acclaimed storyboard artist who takes screenplays and designs storyboard for them."

# character_summary = "\n\n".join([f"Name: {character.name}\nDescription: {character.description}" for character in screenplay.characters])
# scenes_summary = "\n\n".join([f"{i+1}. {scene}" for i, scene in enumerate(screenplay.scenes)])

# prompt = f"""You have been given the following screenplay:

# ---
# ## Synopsis

# {story.synopsis}

# ## Visual Aesthetic

# {story.visual_aesthetic}

# ## Characters 

# {character_summary}

# ## Scenes

# {scenes_summary}

# ---

# Create a list of storyboard frames corresponding to the scenes in the same order. There should usually be 1 frame per scene, but you can have 2 frames for a scene if the action is complex.

# Each frame contains the following things:
# - An image prompt, which simply describes what is happening in the frame, referencing the characters (if any) and action. Do not include dialogue, aesthetic details, or adjectives. This should be very plain and literal.
# - An optional dialogue line, which is spoken by a character, or by a narrator if there is one. If there is nothing spoken here, leave this blank. Aim for around 5-8 seconds of dialogue (around 25-50 words).
# - The name of the character speaking the dialogue, if there is dialogue. If dialogue is blank, leave this also blank. If dialogue is not blank, then this must precisely match the FULL NAME of one of the characters listed in the screenplay, or "Narrator".

# Lastly, in addition to the frame list, write a prompt for a single musical composition that will serve as the background soundtrack for the entire film. The prompt should be densely packed with details about the music, including instruments, mood, tempo, and any other details that a composer would need to know.

# NOTE: dialogue is NOT optional. All frames/clips must have dialogue.
# """

# storyboard = llm(
#     system_message=system_message,
#     prompt=prompt,
#     response_model=Storyboard,
#     model=default_model
# )



# print(story.model_dump_json(indent=2))
# print("----")
# print(screenplay.model_dump_json(indent=2))
# print("----")
# print(storyboard.model_dump_json(indent=2))


# # from utils import make_audiovideo_clip
# # video_url = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/74f4eb185727c3f289d08b07094302b822d0b3ca3b12050517797c2cc339fe98.mp4"
# # audio_url = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/ec4ad5ecade85da38e40523d9c2f93576aa99f312fe6f61aeef53757ee63e925.mp3"
# # clip = make_audiovideo_clip(audio_url, video_url)

# # video_ = utils.get_temp_file(".mp4", video_url)
# # audio_ = utils.get_temp_file(".mp3", audio_url)
# # utils.mix_video_audio(
# #     "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmp6handrte.mp4",
# #     audio_.name,
# #     "test2.mp4"
# # )




# result = txt2img.run({
#     "prompt": story.visual_aesthetic,
#     "width": 1344, 
#     "height": 768
# })
# style_image = result[0]["url"]
# # style_image = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/6f03bc9192a8580239603eb53c7c213a2d68696192dfc4af94eca0d49617c432.png"

# # assumes voices, style_image
# def generate_clip(frame: StoryboardFrame):
#     audio = None
#     duration = 5
    
#     if frame.dialogue:
#         voice_id = voices.get(frame.dialogue_speaker, voice.select_random_voice().voice_id)
#         speech_audio = voice.run(
#             text=frame.dialogue,
#             voice_id=voice_id
#         )
    
#         speech = AudioSegment.from_file(BytesIO(speech_audio))
#         duration = len(speech_audio) / 1000
        
#         # add a bit of silence to both sides
#         extra_time = max(0, 8 - duration) / 2
#         silence1_duration = min(extra_time * 0.3, 0.5)
#         silence2_duration = extra_time - silence1_duration
#         silence1 = AudioSegment.silent(duration=int(1000*silence1_duration))
#         silence2 = AudioSegment.silent(duration=int(1000*silence2_duration))
#         speech = silence1 + speech + silence2
#         duration = len(speech) / 1000

#         audio = BytesIO()
#         speech.export(audio, format="mp3")
    
#     image = txt2img.run({
#         "prompt": frame.image,
#         "width": 1344, 
#         "height": 768,
#         "use_ipadapter": True,
#         "ipadapter_strength": 0.5,
#         "style_image": style_image,
#     })
#     print("image", image)
#     image = image[0]["url"]

#     video = img2vid.run({
#         "image": image,
#         "n_frames": min(64, math.ceil(duration * 8)),
#         "loop": duration > 8,
#     })
#     print("video", video)
#     video = video[0]["url"]
#     # video = "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/74f4eb185727c3f289d08b07094302b822d0b3ca3b12050517797c2cc339fe98.mp4"

#     print("video", video)
#     print("audio", audio)
#     clip = utils.make_audiovideo_clip(video, audio)
#     return clip


# video_output = "themovie_247.mp4"

# video_files = [generate_clip(frame) for frame in storyboard.frames]
# utils.concatenate_videos(video_files, video_output)
# total_duration = utils.get_media_duration(video_output)

# audiocraft = load_tool("tools/audiocraft")
# music = audiocraft.run({
#     "text_input": storyboard.music_prompt,
#     "duration_seconds": total_duration,
#     "model_name": "facebook/musicgen-large"
# })

# response = requests.get(music[0]["url"])
# response.raise_for_status()
# music_audio = AudioSegment.from_file(BytesIO(response.content))
# music_audio -= 12
# music_audio = music_audio.fade_out(duration=min(3000, len(music_audio)))
# music_audio_bytes = music_audio.export(format="mp3").read()

# utils.add_audio_to_audiovideo(video_output, music_audio_bytes, "output317.mp4")
# # # save to tgemp file
# # music_audio.export(f"music1_{ridx}.mp3", format="mp3")

# # audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
# # print("audio_file", audio_file)
# # audio_file.write(response.content)
# # audio_file.flush()







# # utils.mix_video_audio(
# #     f"themovie_{ridx}.mp4",
# #     f"music1_{ridx}.mp3", #audio_file.name,
# #     f"themovie2_{ridx}.mp4",
# # )
# # with open(f"themovie2_{ridx}.mp4", "rb") as f:
# #     video_bytes = f.read()








# # style_image = result[0]["url"]
# # # style_image = "https://dtut5r9j4w7j4.cloudfront.net/7c69136760272ab7106f21c96822d8897e5d6bfadede7ac2460d066cf9f1f47d.png"
# # # style_image = "https://dtut5r9j4w7j4.cloudfront.net/2143c39b0552253376cc6a87ba08e12e6ffe7634e061c9251f0d826c2397d723.png"

# # print("STYLE IMAGE", style_image)
# # print("=====")
# # for scene in scenes.scene_prompts:
# #     prompt = f"{scene}. Style: {scenes.illustration_instructions}"
# #     result = client.create("txt2img", {
# #         "prompt": prompt,
# #         "use_ipadapter": True,
# #         "style_image": style_image,
# #         "ipadapter_strength": 0.5,
# #         "width": 1344, "height": 768
# #     })
# #     print(result)




# #     # except asyncio.CancelledError as e:
# #     #     print("asyncio CancelledError")
# #     #     print(e)
# #     # except Exception as e:
# #     #     print("normal error")
# #     #     print(e)
        
