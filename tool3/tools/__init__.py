from .tool1.handler import tool1
from .tool2.handler import tool2
from .tool3.handler import tool3

__all__ = [
    'tool1',
    'tool2',
    'tool3',
]

handlers = {
    "tool1": tool1,
    "tool2": tool2,
    "tool3": tool3,
}
