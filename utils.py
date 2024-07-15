from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap 
import pathlib
import httpx
import random
import time

import s3


def download_file(url, local_filepath, overwrite=False):
    local_filepath = pathlib.Path(local_filepath)
    local_filepath.parent.mkdir(parents=True, exist_ok=True)

    if local_filepath.exists() and not overwrite:
        print(f"File {local_filepath} already exists. Skipping download.")
        return str(local_filepath)

    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
            if response.status_code == 404:
                raise FileNotFoundError(f"No file found at {url}")
            if response.status_code != 200:
                raise Exception(f"Failed to download from {url}. Status code: {response.status_code}")

            total = int(response.headers["Content-Length"])
            with open(local_filepath, "wb") as f, tqdm(
                total=total, unit_scale=True, unit_divisor=1024, unit="B"
            ) as progress:
                num_bytes_downloaded = response.num_bytes_downloaded
                for data in response.iter_bytes():
                    f.write(data)
                    progress.update(
                        response.num_bytes_downloaded - num_bytes_downloaded
                    )
                    num_bytes_downloaded = response.num_bytes_downloaded
        return str(local_filepath)
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP error occurred while downloading {url}: {e}")
    except Exception as e:
        raise Exception(f"An error occurred while downloading {url}: {e}")
    

def exponential_backoff(
    func,
    max_attempts=5,
    initial_delay=1,
    max_jitter=1,
):
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts:
                raise e
            jitter = random.uniform(-max_jitter, max_jitter)
            print(f"Attempt {attempt} failed. Retrying in {delay} seconds...") 
            time.sleep(delay + jitter)
            delay = delay * 2
            

def mock_image(args):
    image = Image.new("RGB", (300, 300), color="white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    wrapped_text = textwrap.fill(str(args), width=50)
    draw.text((5, 5), wrapped_text, fill="black", font=font)    
    image = image.resize((512, 512), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    buffer_content = buffer.read()
    url = s3.upload_buffer(buffer_content, png_to_jpg=True)
    print(url)
    return [url]