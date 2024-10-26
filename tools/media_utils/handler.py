"""



image transormations
- resize
- crop
- rotate
- flip
- skew ?
- grayscale
- blur
- sharpen
- brightness
- color balance
- gamma correction


image composition
- overlay
- blend / merge
- mask
- add text
- add watermark

video transofrmations
- trim / split
- merge
- adjust fps
- transition effects
- reverse 

audio transofrmations
- trim / split
- merge
- adjust volume
- normalize / equalize
- effects (reverb, echo, distortion, etc.)

compositing
- add audio to video
- replace audio
- replace video

subtitling

"""


import sys
sys.path.append("../..")

import os
from PIL import Image

import eden_utils


async def crop(args: dict, _: str = None):
    image_url = args.get("image")

    image_filename = image_url.split("/")[-1]
    image = eden_utils.download_file(image_url, image_filename)
    image = Image.open(image)

    width, height = image.size
    x, y = width * args.get("x"), height * args.get("y")
    w, h = width * args.get("width"), height * args.get("height")

    image_edited_filename = f"{image_filename}_crop{x}_{y}_{w}_{h}.png"
    if not os.path.exists(image_edited_filename):
        image = image.crop((x, y, x+w, y+h))
        image.save(image_edited_filename)

    result = [image_edited_filename]
    return result
