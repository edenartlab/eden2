#dotenv
from dotenv import load_dotenv
load_dotenv()

import openai
import instructor
from typing import Iterable
from pydantic import BaseModel, Field, ConfigDict
import yaml
from pydantic import BaseModel, Field, create_model
from pydantic.json_schema import SkipJsonSchema
from typing import List, Dict, Any, Union
from typing import List, Optional, Literal
from enum import Enum
from instructor.function_calls import openai_schema



client = instructor.from_openai(openai.OpenAI())


class SyntheticQA(BaseModel):
    """
    This is a synthetic QA pair. And heres the description:
    """
    question: str
    answer: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"question": "What is the capital of France?", "answer": "Paris"},
                {
                    "question": "What is the largest planet in our solar system?",
                    "answer": "Jupiter!!!",
                },
                {
                    "question": "Who wrote 'To Kill a Mockingbird'?",
                    "answer": "Harper Lee!!!",
                },
                {
                    "question": "What element does 'O' represent on the periodic table?",
                    "answer": "Oxygen!!!",
                },
            ]
        }
    )



class Entry(BaseModel):
    """
    This is a synthetic QA ENTRY!!
    """
    qapair: SyntheticQA = Field(..., description="The QA pair yes")
    hello: SkipJsonSchema[Optional[str]] = Field(None, description="The voice id of the character")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "qapair": {
                        "question": "What is the capital of France?",
                        "answer": "Paris",
                    },
                    "hello": "world",
                }
            ]
        }
    )



def get_synthetic_data() -> Iterable[SyntheticQA]:
    return client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Generate synthetic examples"},
            {
                "role": "user",
                "content": "Generate the exact examples you see in the examples of this prompt. ",
            },
        ],
        response_model=Iterable[SyntheticQA],
    )  # type: ignore


if __name__ == "__main__":
    for example in get_synthetic_data():
        print(example)
        """
        question='What is the capital of France?' answer='Paris'
        question='What is the largest planet in our solar system?' answer='Jupiter'
        question="Who wrote 'To Kill a Mockingbird'?" answer='Harper Lee'
        question="What element does 'O' represent on the periodic table?" answer='Oxygen'
        """


from instructor.function_calls import openai_schema
schema = openai_schema(Entry).openai_schema
import json
print(json.dumps(schema, indent=2))




from test6 import *
from instructor.function_calls import openai_schema
schema = openai_schema(Character).openai_schema
import json
print(json.dumps(schema, indent=2))
