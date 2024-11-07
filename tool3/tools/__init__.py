from dotenv import load_dotenv
load_dotenv()

from .tool1.handler import handler as tool1
from .tool2.handler import handler as tool2
from .tool3.handler import handler as tool3

from .media_utils.audio_video_combine.handler import handler as audio_video_combine
from .media_utils.image_concat.handler import handler as image_concat
from .media_utils.image_crop.handler import handler as image_crop
from .media_utils.video_concat.handler import handler as video_concat

from .news.handler import handler as news
from .reel.handler import handler as reel
from .runway.handler import handler as runway
from .story.handler import handler as story
from .hedra.handler import handler as hedra
from .elevenlabs.handler import handler as elevenlabs



# __all__ = [
#     'tool1',
#     'tool2',
#     'tool3',

#     'audio_video_combine',
#     'image_concat',
#     'image_crop',
#     'video_concat',

#     'news',
#     'reel',
#     'runway',
#     'story',
#     'hedra',
# ]

handlers = {
    "tool1": tool1,
    "tool2": tool2,
    "tool3": tool3,

    "audio_video_combine": audio_video_combine,
    "image_concat": image_concat,
    "image_crop": image_crop,
    "video_concat": video_concat,

    "news": news,
    "reel": reel,
    "runway": runway,
    "story": story,
    "hedra": hedra,
    "elevenlabs": elevenlabs,
}

