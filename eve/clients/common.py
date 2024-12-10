from typing import Optional

from eve.agent import Agent


LONG_RUNNING_TOOLS = [
    "txt2vid",
    "style_mixing",
    "img2vid",
    "vid2vid",
    "video_upscale",
    "vid2vid_sdxl",
    "lora_trainer",
    "animate_3D",
    "reel",
    "story",
]


VIDEO_TOOLS = [
    "animate_3D",
    "txt2vid",
    "img2vid",
    "vid2vid_sdxl",
    "style_mixing",
    "video_upscaler",
    "reel",
    "story",
    "lora_trainer",
]


HOUR_IMAGE_LIMIT = 50
HOUR_VIDEO_LIMIT = 10
DAY_IMAGE_LIMIT = 200
DAY_VIDEO_LIMIT = 40

DISCORD_DM_WHITELIST = [
    494760194203451393,
    623923865864765452,
    404322488215142410,
    363287706798653441,
    142466375024115712,
    598627733576089681,
    551619012140990465,
]


def get_agent(agent_path: Optional[str], agent_key: Optional[str], db: str = "STAGE"):
    if agent_path and agent_key:
        raise ValueError("Cannot specify both agent_path and agent_key")
    if agent_path:
        return Agent.from_yaml(str(agent_path), db=db)
    elif agent_key:
        return Agent.load(agent_key, db=db)
    else:
        raise ValueError("Must specify either agent_path or agent_key")
