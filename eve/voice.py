# dotenv
import dotenv
dotenv.load_dotenv()

import os
import random
from tempfile import NamedTemporaryFile
from typing import List, Optional, Dict, Any, Literal, Union
from elevenlabs.client import ElevenLabs, VoiceSettings, Voice
from openai import OpenAI
from typing import Iterator
import instructor
import eden_utils

eleven = ElevenLabs()



def run(
    text: str,
    voice_id: str,    
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    max_attempts: int = 6,
    initial_delay: int = 5,
):
    def generate_with_params():
        return eleven.generate(
            text=text,
            voice=Voice(
                voice_id=voice_id,
                settings=VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=style,
                    use_speaker_boost=use_speaker_boost,
                )
            ),
            model="eleven_multilingual_v2"
        )

    audio = eden_utils.exponential_backoff(
        generate_with_params,
        max_attempts=max_attempts,
        initial_delay=initial_delay,
    )

    if isinstance(audio, Iterator):
        audio = b"".join(audio)

    return audio


def clone_voice(name, description, voice_urls):
    voice_files = []
    for url in voice_urls:
        with NamedTemporaryFile(delete=False) as file:
            file = eden_utils.download_file(url, file.name)
            voice_files.append(file)
    voice = eleven.clone(name, description, voice_files)    
    for file in voice_files:
        os.remove(file)
    return voice


def select_random_voice(
    description: str = None,
    gender: str = None, 
    autofilter_by_gender: bool = False,
    exclude: List[str] = None,
):
    response = eleven.voices.get_all()
    voices = response.voices
    random.shuffle(voices)

    client = instructor.from_openai(OpenAI())

    if autofilter_by_gender and not gender:
        prompt = f"""You are given the following description of a person:

        ---
        {description}
        ---

        Predict the most likely gender of this person."""
        
        gender = client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_model=Literal["male", "female"],
            max_retries=2,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at predicting the gender of a person based on their description.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

    if gender:
        assert gender in ["male", "female"], "Gender must be either 'male' or 'female'"
        voices = [v for v in voices if v.labels.get('gender') == gender]

    if exclude:
        voices = [v for v in voices if v.voice_id not in exclude]
        
    if not description:
        return random.choice(voices)

    voice_ids = {v.name: v.voice_id for v in voices}
    voice_descriptions = "\n".join([f"{v.name}: {', '.join(v.labels.values())}, {v.description or ''}" for v in voices])

    prompt = f"""You are given the follow list of voices and their descriptions.

    ---
    {voice_descriptions}
    ---

    You are given the following description of a desired character:

    ---
    {description}
    ---

    Select the voice that best matches the description of the character."""

    selected_voice = client.chat.completions.create(
        model="gpt-3.5-turbo",
        response_model=Literal[*voice_ids.keys()],
        max_retries=2,
        messages=[
            {
                "role": "system",
                "content": "You are an expert at selecting the right voice for a character.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    return voice_ids[selected_voice]
