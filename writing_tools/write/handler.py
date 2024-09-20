import sys
sys.path.append("../..")
import os
import json
import requests
import instructor
from io import BytesIO
from pydub import AudioSegment
from pydub.utils import ratio_to_db
from pydantic import BaseModel, Field
from openai import OpenAI
from typing import List, Optional, Literal

import s3
import voice
import tool
import utils

client = instructor.from_openai(OpenAI())


async def write(args: dict, user: str = None):
    z = json.dumps(args)
    print(z)
    # return [z]
    return args
