"""
Todo:
- enforce types in contacts
"""
from tool import *


def test_tool():
    tool = Tool.from_dir('example_tool')

    args = tool.prepare_args({
        'type': 'thingy',
        'name': 'John', 
        'price': 1,
        'skills': ["cooking", "swimming"],
        'contacts': [
            {'type': 'emai3l', 'value': 'widget@hotmail.com'},
            {'type': 'phon3e', 'value': '555-1234'},
        ]
    })

    age = args.get('age')  # this was randomly set

    assert args == {
        'name': 'John', 
        'type': 'thingy', 
        'price': 1, 
        'age': age,
        'skills': ['cooking', 'swimming'], 
        'contacts': [
            {'type': 'emai3l', 'value': 'widget@hotmail.com'}, 
            {'type': 'phon3e', 'value': '555-1234'}
        ],
        'address': None, 
        'matrix': None
    }


test_tool()