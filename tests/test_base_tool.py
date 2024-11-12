from eve.tool import Tool


def test_tool():
    tool = Tool.load_from_dir('eve/tools/example_tool')

    args = tool.prepare_args({
        'type': 'thingy',
        'name': 'John', 
        'price': 1,
        'skills': ["cooking", "swimming"],
        'contacts': [
            {'type': 'email', 'value': 'widget@hotmail.com'},
            {'type': 'phone', 'value': '555-1234'},
        ]
    })

    age = args.get('age')  # this was randomly set
    
    assert isinstance(age, int)

    assert args == {
        'name': 'John', 
        'type': 'thingy', 
        'price': 1, 
        'age': age,
        'skills': ['cooking', 'swimming'], 
        'contacts': [
            {'type': 'email', 'value': 'widget@hotmail.com'}, 
            {'type': 'phone', 'value': '555-1234'}
        ],
        'address': None, 
        'matrix': None
    }

