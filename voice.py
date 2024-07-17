import os
import random
from tempfile import NamedTemporaryFile
from typing import List, Optional, Dict, Any, Literal, Union
from elevenlabs.client import ElevenLabs, VoiceSettings, Voice
from openai import OpenAI
from typing import Iterator
import instructor
import utils

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

    audio = utils.exponential_backoff(
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
            file = utils.download_file(url, file.name)
            voice_files.append(file)
    voice = eleven.clone(name, description, voice_files)    
    for file in voice_files:
        os.remove(file)
    return voice


def select_random_voice(
    description: str = None,
    gender: str = None, 
):
    response = eleven.voices.get_all()
    voices = response.voices

    if gender:
        voices = [v for v in voices if v.labels.get('gender') == gender]
    
    if not description:
        return random.choice(voices)
    
    voice_ids = [v.voice_id for v in voices]
    voice_descriptions = "\n".join([f"{v.voice_id}: {v.name}, {v.labels.values()}, {v.description}" for v in voices])
    prompt = f"""You are given the follow list of voices and their descriptions.
    
    ---
    {voice_descriptions}
    ---

    You are given the following description of a desired character:
    
    ---
    {description}
    ---

    Select the voice that best matches the description of the character."""

    client = instructor.from_openai(OpenAI())
    selected_voice = client.chat.completions.create(
        model="gpt-3.5-turbo",
        response_model=Literal[*voice_ids],
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

    return selected_voice
