z={'output': '/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4', 'intermediate_outputs': {'story': {'image_prompt': 'A cinematic asteroid view of Mars hurtling through space and colliding dramatically with Earth, causing an immense explosion.', 'music_prompt': 'Intense orchestral music building to a crescendo, evoking tension and epic disaster.', 'speaker': 'narrator', 'speech': "Witness the catastrophic collision of Mars and Earth, a cosmic dance of destruction, captured with stunning simulation, as the red planet meets our blue world in an inevitable, fiery embrace. Watch as continents crumble and atmospheres collide, forever altering the solar system's story."}, 'characters': [{'name': 'narrator', 'description': 'The narrator of the reel is a voiceover artist who provides some narration for the reel'}], 'images': ['/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4', '/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4'], 'videos': [{'mediaAttributes': {'mimeType': 'video/mp4', 'width': 1280, 'height': 768, 'aspectRatio': 1.6666666666666667, 'duration': 10.54}, 'url': '/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4'}, {'mediaAttributes': {'mimeType': 'video/mp4', 'width': 1280, 'height': 768, 'aspectRatio': 1.6666666666666667, 'duration': 10.54}, 'url': '/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4'}, {'mediaAttributes': {'mimeType': 'video/mp4', 'width': 1280, 'height': 768, 'aspectRatio': 1.6666666666666667, 'duration': 10.54}, 'url': 'https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/1ddbcdbfaa3c4a8ab218a79cbbf1d95f92cc105b0d5e30fe8c5cd0bc8f00bfa4.mp4'}], 'music': [{'mediaAttributes': {'mimeType': 'audio/mpeg', 'duration': 28.044}, 'url': '/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4'}]}}


from eden_utils import upload_result, prepare_result
# from tool import prepare_result
print("z", z)
print("-----")
from pprint import pprint
# pprint(z)
# y=upload_result(z, env="STAGE")
# pprint(y)

# print("======")
# x = prepare_result(z, env="STAGE")
# pprint(x)


# print("======")

# print("======")

# print("======")
# print("======")
# print("======")
# print("======")
# print("======")
# print("======")
# print("======")



# pprint(x)
# print("-----")

# pprint(z)



print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")



m = {
  "output": "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4",
  "intermediate_outputs": {
    "story": {
      "image_prompt": "A cinematic asteroid view of Mars hurtling through space and colliding dramatically with Earth, causing an immense explosion.",
      "music_prompt": "Intense orchestral music building to a crescendo, evoking tension and epic disaster.",
      "speaker": "narrator",
      "speech": "Witness the catastrophic collision of Mars and Earth, a cosmic dance of destruction, captured with stunning simulation, as the red planet meets our blue world in an inevitable, fiery embrace. Watch as continents crumble and atmospheres collide, forever altering the solar systems story."
    },
    "characters": [
      {
        "name": "narrator",
        "description": "The narrator of the reel is a voiceover artist who provides some narration for the reel",
        "bio": "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4"
      }
    ],
    "images": [
      "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4",
      "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4"
    ],
    "music": "/var/folders/h_/8038q2513yz414f7j3yqy_580000gn/T/tmpkjf59iem.mp4"
  }
}



# q = upload_result(m, env="STAGE")

q3 = {'intermediate_outputs': {'characters': [{'bio': {'filename': '0736ba752780ac140185c5007fd2474aaf1cd7be4dc58b49a3b0ffbeb80a0857.mp4',
                                                  'mediaAttributes': {'aspectRatio': 1.6666666666666667,
                                                                      'duration': 28.0,
                                                                      'height': 768,
                                                                      'mimeType': 'video/mp4',
                                                                      'width': 1280}},
                                          'description': 'The narrator of the '
                                                         'reel is a voiceover '
                                                         'artist who provides '
                                                         'some narration for '
                                                         'the reel',
                                          'name': 'narrator'}],
                          'images': [{'filename': '0736ba752780ac140185c5007fd2474aaf1cd7be4dc58b49a3b0ffbeb80a0857.mp4',
                                      'mediaAttributes': {'aspectRatio': 1.6666666666666667,
                                                          'duration': 28.0,
                                                          'height': 768,
                                                          'mimeType': 'video/mp4',
                                                          'width': 1280}},
                                     {'filename': '0736ba752780ac140185c5007fd2474aaf1cd7be4dc58b49a3b0ffbeb80a0857.mp4',
                                      'mediaAttributes': {'aspectRatio': 1.6666666666666667,
                                                          'duration': 28.0,
                                                          'height': 768,
                                                          'mimeType': 'video/mp4',
                                                          'width': 1280}}],
                          'music': {'filename': '0736ba752780ac140185c5007fd2474aaf1cd7be4dc58b49a3b0ffbeb80a0857.mp4',
                                    'mediaAttributes': {'aspectRatio': 1.6666666666666667,
                                                        'duration': 28.0,
                                                        'height': 768,
                                                        'mimeType': 'video/mp4',
                                                        'width': 1280}},
                          'story': {'image_prompt': 'A cinematic asteroid view '
                                                    'of Mars hurtling through '
                                                    'space and colliding '
                                                    'dramatically with Earth, '
                                                    'causing an immense '
                                                    'explosion.',
                                    'music_prompt': 'Intense orchestral music '
                                                    'building to a crescendo, '
                                                    'evoking tension and epic '
                                                    'disaster.',
                                    'speaker': 'narrator',
                                    'speech': 'Witness the catastrophic '
                                              'collision of Mars and Earth, a '
                                              'cosmic dance of destruction, '
                                              'captured with stunning '
                                              'simulation, as the red planet '
                                              'meets our blue world in an '
                                              'inevitable, fiery embrace. '
                                              'Watch as continents crumble and '
                                              'atmospheres collide, forever '
                                              'altering the solar systems '
                                              'story.'}},
 'output': {'filename': '0736ba752780ac140185c5007fd2474aaf1cd7be4dc58b49a3b0ffbeb80a0857.mp4',
            'mediaAttributes': {'aspectRatio': 1.6666666666666667,
                                'duration': 28.0,
                                'height': 768,
                                'mimeType': 'video/mp4',
                                'width': 1280}}}

print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")

# pprint(q)

print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")
print("======================================================")


q = upload_result(m, env="STAGE")


import copy
qwq = copy.deepcopy(q)
r = prepare_result(qwq, env="STAGE", summarize=True)
# pprint(r)

import json
print("======================================================")
print(json.dumps(q, indent=4))
print("======================================================")
print(json.dumps(r, indent=4))
# 

qwq2 = copy.deepcopy(q)
s = prepare_result(qwq2, env="STAGE", summarize=True)
print("======================================================")
print(json.dumps(s, indent=4))
