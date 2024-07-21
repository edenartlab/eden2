import io
import os
import boto3
import hashlib
import mimetypes
import magic
import requests
import tempfile
from pydub import AudioSegment
from typing import Iterator
from PIL import Image

from dotenv import load_dotenv
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")


s3 = boto3.client(
    's3', 
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION_NAME
)


def upload_file_from_url(url, png_to_jpg=False, webp=False, bucket_name=AWS_BUCKET_NAME):
    """Uploads a file to an S3 bucket by downloading it to a temporary file and uploading it to S3."""

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with tempfile.NamedTemporaryFile() as tmp_file:
            for chunk in r.iter_content(chunk_size=1024*1024):
                tmp_file.write(chunk)
            tmp_file.flush()
            tmp_file.seek(0)
            return upload_file(tmp_file.name, png_to_jpg=png_to_jpg, webp=webp, bucket_name=bucket_name)


def upload_file(file_path, png_to_jpg=False, webp=False, bucket_name=AWS_BUCKET_NAME):
    """Uploads a file to an S3 bucket and returns the file URL."""
    
    with open(file_path, 'rb') as file:
        buffer = file.read()

    file_url = upload_buffer(buffer, png_to_jpg, webp, bucket_name)
    print(f"==> Uploaded: {file_url}")
    
    return file_url


def upload_buffer(buffer, png_to_jpg=False, webp=False, bucket_name=AWS_BUCKET_NAME):
    """Uploads a buffer to an S3 bucket and returns the file URL."""
    
    if isinstance(buffer, Iterator):
        buffer = b"".join(buffer)

    # Get sha256 hash of content
    hasher = hashlib.sha256()
    hasher.update(buffer)
    sha = hasher.hexdigest()

    # Get file extension from mimetype
    mime_type = magic.from_buffer(buffer, mime=True)
    file_ext = mimetypes.guess_extension(mime_type)

    # Convert PNG to JPG if requested
    if webp and file_ext != '.webp':
        image = Image.open(io.BytesIO(buffer))
        output = io.BytesIO()
        image.save(output, 'WEBP', quality=95)
        buffer = output.getvalue()
        file_ext = '.webp'
        mime_type = 'image/webp'
    elif png_to_jpg and file_ext == '.png':
        image = Image.open(io.BytesIO(buffer))
        output = io.BytesIO()
        image.convert('RGB').save(output, 'JPEG', quality=95)
        buffer = output.getvalue()
        file_ext = '.jpg'
        mime_type = 'image/jpeg'
    
    # Upload file to S3
    file_name = f"{sha}{file_ext}"
    file_bytes = io.BytesIO(buffer)
    
    s3.upload_fileobj(
        file_bytes, 
        bucket_name, 
        file_name, 
        ExtraArgs={'ContentType': mime_type, 'ContentDisposition': 'inline'}
    )

    # Generate and return file URL
    file_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
    print(f"Uploaded: {file_url}")
    
    return file_url


def upload_audio_segment(audio: AudioSegment, bucket_name=AWS_BUCKET_NAME):
    buffer = io.BytesIO()
    audio.export(buffer, format="mp3")
    output = upload_buffer(buffer, bucket_name=bucket_name)
    return output