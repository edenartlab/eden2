import random
import modal
import instructor
from anthropic import Anthropic
from openai import OpenAI
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, ConfigDict
from fastapi import FastAPI, Depends, HTTPException, Request

import auth
from tool import load_tool
from mongo import get_collection
from models import Story2 as Story

txt2img = load_tool("../workflows/workspaces/img_tools/workflows/txt2img")
img2vid = load_tool("../workflows/workspaces/video/workflows/animate_3D")
flux = load_tool("../workflows/workspaces/flux/workflows/flux-dev")

default_model = "gpt-4-turbo"




genres = [
    "Action", "Adventure", "Comedy", "Drama", "Horror", "Science Fiction", "Fantasy", "Thriller", "Mystery", "Romance", "Western", "Historical Fiction", "Biography (Biopic)", "Documentary", "Musical", "Animation", "Family", "Crime", "Noir", "War", "Epic", "Sports", "Superhero", "Post-Apocalyptic", "Dystopian", "Spy", "Martial Arts", "Film Noir", "Cyberpunk", "Steampunk", "Zombie", "Slasher", "Psychological Horror", "Body Horror", "Gothic", "Paranormal", "Mockumentary", "Coming-of-Age", "Road Movie", "Buddy Comedy", "Romantic Comedy", "Dark Comedy", "Satire", "Parody", "Black Comedy", "Melodrama", "Political Drama", "Courtroom Drama", "Social Drama", "Period Piece", "Historical Epic", "Swashbuckler", "Heist", "Gangster", "Detective", "Neo-Noir", "Erotic Thriller", "Survival", "Disaster", "Space Opera", "Alien Invasion", "Time Travel", "Techno-Thriller", "Psychological Thriller", "Legal Thriller", "Conspiracy Thriller", "Revenge Thriller", "Religious", "Mythological", "Sword and Sorcery", "Fairy Tale", "Urban Fantasy", "High Fantasy", "Low Fantasy", "Grimdark", "Sword and Sandal", "Historical Romance", "Caper", "Art Film", "Avant-Garde", "Experimental", "Absurdist", "Metafiction", "Magical Realism", "Surrealist", "Folk Horror", "Eco-Horror", "Splatter", "Exploitation", "Blaxploitation", "Spaghetti Western", "Samurai", "Kaiju", "Mecha", "Jidaigeki", "Chanbara", "Tokusatsu", "Yakuza", "Giallo", "Psychotronic", "Pulp", "Grindhouse", "Vigilante", "Stoner Comedy", "Teen Comedy", "Gross-Out Comedy", "Screwball Comedy", "Slapstick", "Romantic Fantasy", "Dieselpunk", "Retrofuturism", "Afrofuturism", "Climate Fiction", "Anthology", "Docudrama", "Docufiction", "Music Documentary", "Rockumentary", "Concert Film", "Road Comedy", "Space Western", "Biopunk", "Hard Sci-Fi", "Soft Sci-Fi", "Speculative Fiction", "Alternate History", "Parallel Universe", "Wuxia", "B-Movie", "Cult Film", "Midnight Movie", "Exploitation Horror", "Mumblecore", "Southern Gothic", "Tropical Gothic", "Tech-Noir", "Weird Fiction", "Weird Western", "Ghost Story", "Haunted House", "Found Footage", "Monster Movie", "Creature Feature", "Kaiju (Giant Monster)", "Beach Party", "Troma Film", "Lynchian", "Spiritual Film", "Christmas Film", "Folk Fantasy", "Folk Comedy", "Neo-Western", "Splatter Western", "Urban Thriller", "Legal Comedy", "Tragicomedy", "Philosophical Drama", "Tech Drama", "Teen Drama", "Teen Horror", "Found Footage Horror", "Creature Horror", "Cryptid Thriller", "Postmodern Comedy", "Hyperrealism", "Slow Cinema", "Dance Film", "Magical Girl", "Musical Fantasy", "War Comedy", "War Drama", "Disaster Comedy", "Underwater Horror", "Nature Horror", "Art Horror", "New Wave Cinema", "Poetic Realism", "Minimalist Film", "Industrial Sci-Fi", "Cyber Horror", "Mecha Anime", "Japanese New Wave", "French New Wave", "Italian Neorealism", "Soviet Montage", "Feminist Film", "Queer Cinema", "Drag Film", "Experimental Horror", "Anarchist Cinema", "Guerrilla Filmmaking", "Road Horror", "Satanic Panic", "Ethnographic Film", "Hyperviolent Cinema", "Stoner Horror", "Shockumentary", "Immersive Cinema", "Punk Cinema", "Vigilante Horror", "Poverty Row Cinema", "Neo-Surrealism", "Z-movie", "Ethereal Drama", "Grindhouse Sci-Fi", "Biker Film", "Gritty Urban Drama", "Pre-Code Hollywood", "Video Nasty", "Mondo Film", "Gritty Realism", "Nature Documentary", "Shock Horror", "Demonic Possession Horror", "Cult Musical", "Psychedelic Western", "Proletariat Cinema", "New Queer Cinema", "Yakuza Horror", "Pinku Eiga (Japanese Softcore)", "Nunsploitation", "Clergy Thriller", "Apocalyptic Horror", "Existential Horror", "Dance Horror", "Black Romantic Comedy", "Ethnic Comedy", "Crime Melodrama", "Drug Cartel Drama", "Slavic Mythological Film", "Folkloric Fantasy", "Drone Film", "Structural Film", "Cyberdelic", "Guerilla Documentary", "Bizarro Fiction Adaptation", "Demonic Comedy", "Situational Thriller", "Fever Dream Cinema", "Mad Scientist Horror", "Art Porn", "Erotic Sci-Fi", "Blended Genre Mashup", "Contemporary Folk Horror", "Swordplay Film", "Lost World Adventure", "Dadaist Film", "Corporate Thriller", "Neo-Western", "Acid Western", "Space Western", "Revisionist Western", "Weird West", "Ostern (Eastern European Western)", "Psychological Western", "Vampire Western", "Chopsocky", "Gun Fu", "Girls with Guns", "Heroic Bloodshed", "Wuxia", "Jidaigeki", "Samurai Cinema", "Ninja Film", "Pirate Film", "Swashbuckler", "Cape and Sword", "Peplum (Sword and Sandal)", "Historical Epic", "Biblical Epic", "Mythological Film", "Folklore Film", "Fairy Tale Film", "Urban Fantasy", "Contemporary Fantasy", "Dark Fantasy", "High Fantasy", "Low Fantasy", "Magical Realism", "Rubber Reality", "Isekai (Other World)", "Portal Fantasy", "Sword and Planet", "Planetary Romance", "Space Opera", "Hard Science Fiction", "Soft Science Fiction", "Dieselpunk", "Atompunk", "Nanopunk", "Solarpunk", "Stonepunk", "Clockpunk", "Nowpunk", "Retro-Futurism", "Alternate History", "Uchronia", "Time Travel", "Parallel Universe", "Multiverse", "Metaphysical Film", "Existential Film", "Philosophical Fiction", "Slice of Life", "Kitchen Sink Drama", "Social Realism", "Neorealism", "Hyperrealism", "Magic Realism", "Poetic Realism", "Transcendental Style", "Slow Cinema", "Contemplative Cinema", "Cinema of Transgression", "New Queer Cinema", "Third Cinema", "Fourth Cinema", "Fifth Cinema", "Imperfect Cinema", "Accented Cinema", "Transnational Cinema", "Diasporic Cinema", "Exilic Cinema", "Intercultural Cinema", "Global Cinema", "World Cinema", "National Cinema", "Regional Cinema", "Indigenous Cinema", "Ethnographic Fiction", "Ethno-Fiction", "Ethnofuturism", "Afrofuturism", "Chicano Futurism", "Gulf Futurism", "Sinofuturism", "Gendai-geki (Contemporary Setting Films)", "Mecha (Giant Robot Films)", "Iyashikei (Healing Films)", "Nikkatsu Action", "Pinky Violence", "Action", "Adventure", "Disaster", "Martial Arts", "Military Action", "Spy and Espionage", "Superhero", "Video game movies", "Action comedy (including Buddy movie)", "Action crime", "Action drama", "Action-horror", "Action thriller", "Animation", "Claymation and Stop Motion", "Cutout Animation", "Traditional Drawn Animation", "Live-Action Hybrid", "Puppet Animation", "Comedy", "Black or Dark Comedy", "Buddy Comedy", "Hangout Movies", "Parody and Spoof", "Prank Movies", "Satire", "Slapstick Comedy", "Screwball Comedy", "Crime", "Cop Movies", "Crime Drama", "Crime Thriller", "Detective and Whodunnit", "Gangster Films", "Hardboiled", "Heist and Caper", "Documentary", "Expository Documentary", "Observational Documentary", "Poetic Documentary", "Participatory Documentary", "Reflexive Documentary", "Performative Documentary", "Drama", "Docudrama", "Melodrama", "Teen Drama", "Medical Drama", "Legal Drama", "Religious Drama", "Sports Drama", "Political Drama", "Anthropological Drama","Philosophical Drama", "Fantasy", "Contemporary and Urban Fantasy", "Epic Fantasy", "Fairy Tale", "Dark Fantasy", "History", "Historical Film", "Period Film", "Alternate History", "Biography (Biopic)", "Horror", "Ghost", "Zombie", "Werewolf", "Vampire", "Monster", "Slasher", "Splatter and Gore", "Body Horror", "Folk Horror", "Occult", "Found Footage", "Outbreak", "Music Film and Musical", "Romance", "Historical Romance", "Regency Romance", "Romantic Drama", "Romantic Comedy", "Chick Flick", "Fantasy Romance", "Science Fiction", "Space Opera or Epic Sci-Fi", "Utopia", "Dystopia", "Contemporary Sci-Fi", "Cyberpunk", "Steampunk", "Thriller", "Psychological Thriller", "Mystery", "Film Noir", "Neo-noir", "War", "Western", "Spaghetti Western", "Revisionist Western"
]

story_examples = [
    {
        "synopsis": "In medieval Japan, a dishonored samurai seeks redemption by protecting a village from a band of ruthless warlords, uncovering a conspiracy that could change the course of history",
        "visual_aesthetic": "Traditional Japanese aesthetic, sumi-e ink wash technique, moody, muted earthy colors",
        "poster": "A panoramic view of a Japanese village nestled in misty mountains. In the foreground, a lone samurai stands on a hill, his back to the viewer, sword at his side. His silhouette is sharply contrasted against the soft, watercolor-like landscape. In the distance, ominous storm clouds gather, with faint outlines of armored horsemen emerging from the mist. The entire scene is rendered in muted earthy tones, resembling a large-scale sumi-e ink painting with delicate brushstrokes visible throughout."
    },
    {
        "synopsis": "A documentary traces the enduring cultural, economic, and technological legacies of the ancient Silk Road, exploring how this network of trade routes disseminated ideas, beliefs, and technologies that shaped the civilizations of Europe, Asia, and the Middle East.",
        "visual_aesthetic": "Photorealistic, high contrast, cinematic, panoramic, 35mm film grain, Mediterannean",
        "poster": "A sweeping desert landscape at sunset, with golden sand dunes in the foreground transitioning to rocky mountains in the background. A winding path, representing the Silk Road, cuts through the scene. Along this path, a series of vignettes blend seamlessly: a Greek temple, a Chinese pagoda, Persian gardens, and Indian stupas. Caravans of camels and merchants dot the route. Grainy, high-contrast look reminiscent of 35mm film, with rich, warm Mediterranean colors."
    },
    {
        "synopsis": "When a tech-obsessed family's devices magically come to life during a camping trip, they must learn to reconnect with each other and nature to find their way back home.",
        "visual_aesthetic": "Vibrant color palette, stylized CGI creatures, lush forest landscapes, cozy cabin interiors, nostalgic Polaroid-style transitions, soft focus",
        "poster": "A split-screen effect dividing the poster diagonally. On one side, a lush, vibrant forest with exaggerated, cartoonish trees and oversized flora. On the other, a cozy log cabin interior. Animated gadgets with comical faces (phones, tablets, laptops) seem to be escaping from the cabin into the forest. A family of four is caught in the middle, their expressions a mix of surprise and wonder. The whole scene is rendered in a bright, saturated palette with a slight Polaroid-like border and soft focus edges."
    },
    {
        "synopsis": "In a withering rural town, an introverted botanist cultivates a garden of extinct plants, forming an unexpected bond with a curious local child that challenges her isolation and rekindles hope in a community on the brink of disappearing.",
        "visual_aesthetic": "Muted earth tones, soft natural light, extreme botanical close-ups, shallow depth of field, grainy film texture, lingering static shots, desaturated palette, golden hour lens flares, weathered rural aesthetic",
        "poster": "A greenhouse interior bathed in golden hour light. In the center, an elderly botanist and a young child lean over a workbench, examining a rare, luminescent plant. Rays of sunlight stream through glass panes, creating a soft, hazy atmosphere. Surrounding them are shelves filled with an assortment of extinct plants. Rendered in muted earth tones with a grainy, vintage film texture overlaid."
    },
    {
        "synopsis": "In a dystopian future where memories can be bought and sold, a young rebel seeks to dismantle the corporation controlling these transactions, only to discover that her memory is being covertly manipulated by the very corporation she seeks to undermine.",
        "visual_aesthetic": "Dark, gritty, cyberpunk, concrete jungle, sketchy, matte anime feel", 
        "poster": "A fractured cityscape of towering skyscrapers and neon billboards, reflected in a giant puddle on a rainy street. The reflection is distorted, revealing glimpses of hidden memories and alternate realities. In the foreground, the silhouette of a woman faces away from the viewer, her head partially transparent, filled with glowing synapses and fragmented memory images. The entire scene is rendered in a dark, gritty style with a matte anime aesthetic, dominated by deep blues and purples punctuated by stark neon highlights."
    },
]

class StoryIdea(BaseModel):
    logline: str = Field(
        ..., 
        description="A concise but specific 1-2 sentence summary of the film, focusing on the central premise or conflict of the story."
    )
    visual_aesthetic: str = Field(
        ..., 
        description="A short sentence consisting of phrases that describe the aesthetic or visual characteristics, including but not limited to medium, genre, lighting, illustration technique, color pallette, mood, and other visual elements. **Do not** include and people or descriptions reminding one of people, nor any plot elements, or sound design. Just focus on visual characteristics that specifically distinguish this film visually from others."
    )
    poster: str = Field(
        ...,
        description="A precise order to an illustrator to create a landscape-orientation poster for the film to be used in a movie theater lobby. Must be 1-3 sentences maximum. The illustrators are making a quintessential depiction of the film, succinctly capturing the logline in a single scene. Your instruction to the illustrator must focus *only* on the *content* of the scene. Do not focus on plot or story, just a single quintessential scene. Do not reference the poster itself, just focus on the image."
    )
    stills: Optional[List[str]] = Field(
        ...,
        description="A list of 3-5 posters, still images that best describe key scenes in the film. These should be structured just like the poster."
    )
    model_config = ConfigDict(json_schema_extra={"examples": story_examples})



class StoryboardStills(BaseModel):
    stills: Optional[List[str]] = Field(
        ...,
        description="A list of 3-5 posters, still images that best describe key scenes in the film. These should be structured just like the poster."
    )


def llm(
    system_message: str, 
    prompt: str, 
    response_model: BaseModel, 
    model: Literal["gpt-3.5-turbo", "gpt-4-turbo", "claude-3-5-sonnet-20240620"]
):
    provider = "openai" if model.startswith("gpt") else "anthropic"

    if provider == "anthropic":
        claude = instructor.from_anthropic(Anthropic())
        result = claude.messages.create(
            model=model,
            max_tokens=8192,
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



def react(
    request: dict, 
    _: dict = Depends(auth.authenticate_abraham_admin)
):
    try:
        story_id = request.get("story_id")
        story = Story.from_id(story_id, env="ABRAHAM")
        action = request.get("action")
        assert action in ["praise", "unpraise", "burn", "unburn"], "Invalid action"
        if action == "praise":
            story.praise(request.get("user"))
            return story.praises
        elif action == "unpraise":
            story.unpraise(request.get("user"))
            return story.praises
        elif action == "burn":
            story.burn(request.get("user"))
            return story.burns
        elif action == "unburn":
            story.unburn(request.get("user"))
            return story.burns
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))


def bless(
    request: dict, 
    _: dict = Depends(auth.authenticate_abraham_admin)
):
    try:
        story_id = request.get("story_id")
        story = Story.from_id(story_id, env="ABRAHAM")
        blessing = request.get("blessing")
        story.bless(blessing, request.get("user"))
        return story.blessings
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))




def generate_story():
    genre = random.choice(genres)
    prompt = f"Come up with an idea for a film whose genre is {genre}. The idea is presented with the following three elements: the logline, the visual aesthetic, and the poster. Leave the stills blank."
    story = llm(
        system_message="You are a critically acclaimed filmmaker who conceives ideas for films.",
        prompt=prompt,
        response_model=StoryIdea,
        model=default_model
    )
    print("story", story)
    result = flux.run({
        "prompt": story.poster,
        "width": 1344, 
        "height": 768
    })
    print("result", result)
    if "url" in result[0]:
        poster_image = result[0]["url"]
    else:
        filename = result[0]["filename"]
        poster_image = f"https://edenartlab-stage-data.s3.amazonaws.com/{filename}"
    story_document = Story(env="ABRAHAM")
    story_document.update_current({
        "genre": genre,
        "logline": story.logline, 
        "visual_aesthetic": story.visual_aesthetic, 
        "poster": story.poster,
        "poster_image": poster_image,
        "stills": None
    })
    if random.random() < 0.5:
        generate_stills(story_document.id)



def generate_stills(story_id: str):
    story_document = Story.from_id(story_id, env="ABRAHAM")
    prompt = f"""You are given the following story: {story_document.current["logline"]}. 
    
    The visual aesthetic is {story_document.current["visual_aesthetic"]}. 

    Here is the image for the poster: {story_document.current["poster_image"]}.
    
    Come up with 3-5 still images that best describe key scenes in the film. Each still image should be a precise order to an illustrator to create stills which will be used to guide the storyboard development. Each should be structured just like the poster image.
    
    Do not change any of the other elements of the story. Leave Just come up with 3-5 still images that best describe key scenes in the film.
    """

    print("prompt", prompt)

    storyboard_stills = llm(
        system_message="You are a critically acclaimed filmmaker who generates storyboards for films.",
        prompt=prompt,
        response_model=StoryboardStills,
        model=default_model
    )
    print("storyboard_stills", storyboard_stills)
    stills = []
    for still in storyboard_stills.stills:
        # stills.append(still)
        result = flux.run({
            "prompt": f"{still}. {story_document.current['visual_aesthetic']}",
            "width": 1344, 
            "height": 768
        })
        print("result", result)
        if "url" in result[0]:
            still = result[0]["url"]
        else:
            filename = result[0]["filename"]
            still = f"https://edenartlab-stage-data.s3.amazonaws.com/{filename}"
        stills.append(still)
    story_document.update_current({
        "stills": stills
    })


"""
send back users for blessings
how to store user auth info
deployment
""" 


def get_story(story_id: str):
    story = Story.from_id(story_id, env="ABRAHAM").model_dump()
    print("story", story)
    return {
        "id": str(story["id"]),
        "logline": story["current"]["logline"],
        "poster_image": story["current"]["poster_image"],
        "poster_thumbnail": story["current"]["poster_image"].replace(".png", "_768.webp"),
        "praises": story["praises"],
        "burns": story["burns"],
        "blessings": story["blessings"],
        "stills": story["current"].get("stills", None)
    } 

def get_stories():
    stories = [
        {
            "id": str(story["_id"]),
            "logline": story["current"]["logline"],
            "poster_image": story["current"]["poster_image"],
            "poster_thumbnail": story["current"]["poster_image"].replace(".png", "_768.webp"),
            "praises": story["praises"],
            "burns": story["burns"],
            "blessings": story["blessings"],
            "stills": story["current"].get("stills", None)
        } 
        for story in get_collection(
            "stories", env="ABRAHAM").find().sort("createdAt", -1).limit(10)
    ]
    return stories

app = modal.App(
    name="abraham",
    secrets=[
        modal.Secret.from_name("admin-key"),
        # modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("gcp-credentials"),
        # modal.Secret.from_name("replicate"),
        # modal.Secret.from_name("sentry"),
    ],   
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"ENV": "STAGE"})
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "ffmpeg")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor[anthropic]", 
                 "anthropic", "fastapi==0.103.1", "requests", "pyyaml", "python-dotenv", "replicate", "boto3", "python-magic", "Pillow", "pydub", "sentry_sdk", "google-cloud-aiplatform", "moviepy", "pymongo")
    # .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_mount(modal.Mount.from_local_dir("../workflows"), remote_path="/workflows")
)

web_app = FastAPI()
web_app.get("/get_stories")(get_stories)
web_app.get("/get_story/{story_id}")(get_story)
# web_app.post("/praise")(handle_praise)
web_app.post("/react")(react)
web_app.post("/bless")(bless)




@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=3,
    container_idle_timeout=60,
    timeout=60
)
@modal.asgi_app()
def fastapi_app():
    return web_app

@app.function(
    image=image,
    schedule=modal.Period(hours=6)
)
def generate_story_task():
    generate_story()


@app.local_entrypoint()
def run_locally():
    generate_story_task.remote()

# if __name__ == "__main__":
#     modal.runner.deploy_stub(generate_story_task)
#     run_locally()



"""
curl -X POST https://edenartlab--abraham-fastapi-app-dev.modal.run/react \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer ABE_CODE" \
     -d '{"story_id": "66e71379db70d891682e7800", "action": "unpraise", "user": "test_user_1"}'
"""


"""


curl -X POST https://edenartlab--abraham-fastapi-app.modal.run/react \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer ABE_CODE" \
     -d '{"story_id": "66e71379db70d891682e7800", "action": "unpraise", "user": "test_user_1"}'


"""



"""


curl -X POST https://edenartlab--abraham-fastapi-app.modal.run/bless \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer ABE_CODE" \
     -d '{"story_id": "66e71379db70d891682e7800", "blessing": "That was pretty good", "user": "test_user_1"}'


     

curl -X POST https://edenartlab--abraham-fastapi-app-dev.modal.run/bless \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer bg971fn8X63nuVDSIAmEN19btcBrHYksxYewy6WKP4M=" \
     -d '{"story_id": "67075e667825b5fe6a1f8627", "blessing": "That was pretty good", "user": "test_user_1"}'

     

curl -X POST https://edenartlab--abraham-fastapi-app-dev.modal.run/bless \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer mAFxJCN7Q_aV6GBm_KGa4A2ufBYqoD7I832FxH_jvw1B" \
     -d '{"story_id": "67075e667825b5fe6a1f8627", "blessing": "That was pretty good", "user": "test_user_1"}'


"""