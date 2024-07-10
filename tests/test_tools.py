import asyncio
import sys
sys.path.append(".")

from tools import get_tools, load_tool

# load all tools into dictionary
tools = get_tools("../workflows", exclude=["blend"])

txt2img = tools["txt2img"]
print(txt2img.name, txt2img.description)
for param in txt2img.parameters:
    print(f"{param.name} : {param.description}")


# you can also load a single tool
txt2vid = load_tool("../workflows/txt2vid")
print(txt2vid.name, txt2vid.description)
for param in txt2vid.parameters:
    print(f"{param.name} : {param.description}")


# execute a tool
async def test_tool():
    args = txt2img.test_args()
    result = await txt2img.run("txt2img", args)
    print(result)

asyncio.run(test_tool())


# mock execute a tool
async def run_mock_tool():
    txt2img.mock = True
    args = txt2img.test_args()
    result = await txt2img.run("txt2img", args)
    print(result)

asyncio.run(run_mock_tool())
