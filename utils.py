import os
import re
import time
import math
import magic
import httpx
import base64
import random
import pathlib
import textwrap
import requests
import tempfile
import subprocess
import numpy as np
from moviepy.editor import VideoFileClip
from tqdm import tqdm
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import s3


def get_media_attributes(file_path):
    def process_thumbnail(thumbnail):
        width, height = thumbnail.size
        aspect_ratio = width / height
        if height > 512:
            tw, th = int(512 * aspect_ratio), 512
            thumbnail = thumbnail.resize((tw, th))
        return thumbnail, width, height, aspect_ratio
    
    url = file_path.startswith('http://') or file_path.startswith('https://')
    if url:
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        file_path = download_file(file_path, temp_file.name, overwrite=True)

    mime_type = magic.from_file(file_path, mime=True)
    media_attributes = {
        "mimeType": mime_type,
    }

    if 'image' in mime_type:
        image = Image.open(file_path)
        thumbnail = image.copy()
        thumbnail, width, height, aspect_ratio = process_thumbnail(thumbnail)
        media_attributes.update({
            "width": width,
            "height": height,
            "aspectRatio": aspect_ratio
        })

    elif 'video' in mime_type:
        video = VideoFileClip(file_path)
        thumbnail = Image.fromarray(video.get_frame(0).astype('uint8'), 'RGB')
        thumbnail, width, height, aspect_ratio = process_thumbnail(thumbnail)
        media_attributes.update({
            "width": width,
            "height": height,
            "aspectRatio": aspect_ratio,
            "duration": video.duration
        })

    elif 'audio' in mime_type:
        thumbnail = None
        media_attributes.update({
            "duration": get_media_duration(file_path)
        })

    if url:
        os.remove(file_path)

    return media_attributes, thumbnail


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
    buffer = PIL_to_bytes(image)
    url = s3.upload_buffer(buffer, png_to_jpg=True)
    return [url]


def get_media_duration(video_file):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        video_file,
    ]
    duration = subprocess.check_output(cmd).decode().strip()
    return float(duration)


def get_font(font_name, font_size):
    font_path = os.path.join(os.path.dirname(__file__), "fonts", font_name)
    font = ImageFont.truetype(font_path, font_size)
    return font


def text_to_lines(text):
    pattern = r"^\d+[\.:]\s*\"?"
    lines = [line for line in text.split("\n") if line]
    lines = [
        re.sub(pattern, "", line, flags=re.MULTILINE) 
        for line in lines
    ]
    return lines


def download_image_to_PIL(url):
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    return image


def PIL_to_bytes(image, ext="JPEG", quality=95):
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=ext, quality=quality)
    return img_byte_arr.getvalue()


def file_to_base64_data(file_path, max_size, quality=95, truncate=False):
    img = Image.open(file_path).convert('RGB')
    if isinstance(max_size, (int, float)):
        w, h = img.size
        ratio = min(1.0, ((max_size ** 2) / (w * h)) ** 0.5)
        max_size = int(w * ratio), int(h * ratio)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    img_bytes = PIL_to_bytes(img, ext="JPEG", quality=quality)
    data = base64.b64encode(img_bytes).decode("utf-8")
    if truncate:
        data = data[:64]+"..."
    return data


def calculate_target_dimensions(images, max_pixels):
    min_w = float("inf")
    min_h = float("inf")

    total_aspect_ratio = 0.0

    for image_url in images:
        image = download_image_to_PIL(image_url)
        width, height = image.size
        min_w = min(min_w, width)
        min_h = min(min_h, height)
        total_aspect_ratio += width / height

    avg_aspect_ratio = total_aspect_ratio / len(images)

    if min_w / min_h > avg_aspect_ratio:
        target_height = min_h
        target_width = round(target_height * avg_aspect_ratio)
    else:
        target_width = min_w
        target_height = round(target_width / avg_aspect_ratio)

    if target_width * target_height > max_pixels:
        ratio = (target_width * target_height) / max_pixels
        ratio = math.sqrt((target_width * target_height) / max_pixels)
        target_width = round(target_width / ratio)
        target_height = round(target_height / ratio)

    target_width -= target_width % 2
    target_height -= target_height % 2

    return target_width, target_height


def resize_and_crop(image, width, height):
    target_ratio = width / height
    orig_width, orig_height = image.size
    orig_ratio = orig_width / orig_height

    if orig_ratio > target_ratio:
        new_width = int(target_ratio * orig_height)
        left = (orig_width - new_width) // 2
        top = 0
        right = left + new_width
        bottom = orig_height
    else:
        new_height = int(orig_width / target_ratio)
        top = (orig_height - new_height) // 2
        left = 0
        bottom = top + new_height
        right = orig_width

    image = image.crop((left, top, right, bottom))
    image = image.resize((width, height), Image.LANCZOS)

    return image


def create_dialogue_thumbnail(image1_url, image2_url, width, height, ext="WEBP"):
    image1 = download_image_to_PIL(image1_url)
    image2 = download_image_to_PIL(image2_url)

    half_width = width // 2

    image1 = resize_and_crop(image1, half_width, height)
    image2 = resize_and_crop(image2, half_width, height)

    combined_image = Image.new("RGB", (width, height))

    combined_image.paste(image1, (0, 0))
    combined_image.paste(image2, (half_width, 0))

    img_byte_arr = BytesIO()
    combined_image.save(img_byte_arr, format=ext)

    return img_byte_arr.getvalue()


def concatenate_videos(video_files, output_file, fps=30):
    converted_videos = []
    for video in video_files:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp:
            output_video = temp.name
            convert_command = [
                "ffmpeg", "-y", "-loglevel", "panic",
                "-i", video, "-r", str(fps), "-c:a", "copy",
                output_video
            ]
            subprocess.run(convert_command)
            converted_videos.append(output_video)
    filter_complex = "".join(
        [f"[{i}:v] [{i}:a] " for i in range(len(converted_videos))],
    )
    filter_complex += f"concat=n={len(converted_videos)}:v=1:a=1 [v] [a]"
    concat_command = ["ffmpeg"]
    for video in converted_videos:
        concat_command.extend(["-i", video])
    concat_command.extend(
        [
            "-y", "-loglevel", "panic",
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
            output_file,
        ],
    )
    subprocess.run(concat_command)
    for video in converted_videos:
        os.remove(video)


def mix_video_audio(video_path, audio_path, output_path):
    cmd = [
        "ffmpeg", "-y", 
        "-i", video_path, "-i",audio_path,
        "-filter_complex", "[1:a]volume=1.0[a1];[0:a][a1]amerge=inputs=2[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-ac", "2",
        output_path,
    ]
    subprocess.run(cmd, check=True)


def combine_audio_video(audio_input, video_input):
    def get_temp_file(suffix, input_data):
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=True)
        if isinstance(input_data, str):  # URL
            subprocess.run(["wget", "-nv", "-O", temp_file.name, input_data])
        elif isinstance(input_data, BytesIO):  # BytesIO
            with open(temp_file.name, 'wb') as f:
                f.write(input_data.getvalue())
        return temp_file

    audio_file = get_temp_file(".mp3", audio_input)
    video_file = get_temp_file(".mp4", video_input)
    output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)

    # get the duration of the audio file
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        audio_file.name,
    ]
    audio_duration = subprocess.check_output(cmd).decode().strip()

    # loop the video
    looped_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "panic", "-stream_loop", "-1", 
        "-i", video_file.name,
        "-c", "copy", "-t", audio_duration,
        looped_video.name,
    ]
    subprocess.run(cmd)

    # merge the audio and the looped video
    cmd = [
        "ffmpeg", "-y", "-loglevel", "panic",
        "-i", looped_video.name,
        "-i", audio_file.name,
        "-c:v", "copy", "-c:a", "aac", "-strict", "experimental","-shortest",
        output_file.name,
    ]
    subprocess.run(cmd)

    return output_file.name


def stitch_image_video(image_file: str, video_file: str, image_left: bool = False):
    output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)

    if image_left:
        filter_complex = '"[1:v][0:v]scale2ref[img][vid];[img]setpts=PTS-STARTPTS[imgp];[vid]setpts=PTS-STARTPTS[vidp];[imgp][vidp]hstack"'
    else:
        filter_complex = '"[0:v][1:v]scale2ref[vid][img];[vid]setpts=PTS-STARTPTS[vidp];[img]setpts=PTS-STARTPTS[imgp];[vidp][imgp]hstack"'

    cmd = [
        "ffmpeg", "-y", "-loglevel", "panic",
        "-i", video_file, "-i", image_file,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_file.name,
    ]
    subprocess.run(cmd)

    return output_file.name


def process_in_parallel(array, func, max_workers=3):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(func, item, index): index
            for index, item in enumerate(array)
        }
        results = [None] * len(array)
        for future in as_completed(futures):
            try:
                index = futures[future]
                results[index] = future.result()
            except Exception as e:
                print(f"Task error: {e}")
                for f in futures:
                    f.cancel()
                raise e
    return results


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        if draw.textlength(" ".join(current_line + [word]), font=font) > max_width:
            lines.append(" ".join(current_line))
            current_line = [word]
        else:
            current_line.append(word)
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def video_textbox(
    paragraphs: list[str],
    width: int,
    height: int,
    duration: float,
    fade_in: float,
    font_size: int = 36,
    font_ttf: str = "Arial.ttf",
    margin_left: int = 25,
    margin_right: int = 25,
    line_spacing: float = 1.25,
):
    from moviepy.editor import ImageClip, TextClip, AudioClip
    
    font = get_font(font_ttf, font_size)

    canvas = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(0, 0), (width, height)], fill="black")

    y = 100
    for text in paragraphs:
        wrapped_text = wrap_text(draw, text, font, width - margin_left - margin_right)
        for line in wrapped_text:
            draw.text((margin_left, y), line, fill="white", font=font)
            y += int(line_spacing * font.size)
        y += int(line_spacing * font.size)

    image_np = np.array(canvas)
    clip = ImageClip(image_np, duration=duration)
    clip = clip.fadein(fade_in).fadeout(fade_in)

    # Create a silent audio clip and set it as the audio of the video clip
    silent_audio = AudioClip(lambda t: [0, 0], duration=duration, fps=44100)
    clip = clip.set_audio(silent_audio)

    output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    clip.write_videofile(output_file.name, fps=30, codec="libx264", audio_codec="aac")

    return output_file.name


def custom_print(string, color):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m"
    }
    return f"{colors[color]}{string}\033[0m"
    