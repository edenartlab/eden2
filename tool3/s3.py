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

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME")
AWS_BUCKET_NAME_STAGE = os.getenv("AWS_BUCKET_NAME_STAGE")
AWS_BUCKET_NAME_PROD = os.getenv("AWS_BUCKET_NAME_PROD")


s3 = boto3.client(
    's3', 
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION_NAME
)

s3_buckets = {
    "STAGE": AWS_BUCKET_NAME_STAGE,
    "PROD": AWS_BUCKET_NAME_PROD,
}

file_extensions = {
    'audio/mpeg': '.mp3',
    'audio/mp4': '.mp4',
    'audio/flac': '.flac',
    'audio/wav': '.wav',
    'image/jpeg': '.jpg',
    'image/webp': '.webp',
    'image/png': '.png',
    'video/mp4': '.mp4',
    'application/x-tar': '.tar',
    'application/zip': '.zip'
}


def get_root_url(env="STAGE"):
    """Returns the root URL for the specified bucket."""
    bucket_name = s3_buckets[env]
    return f"https://{bucket_name}.s3.{AWS_REGION_NAME}.amazonaws.com"
    
    
def upload_file_from_url(url, name=None, file_type=None, env="STAGE"):
    """Uploads a file to an S3 bucket by downloading it to a temporary file and uploading it to S3."""

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with tempfile.NamedTemporaryFile() as tmp_file:
            for chunk in r.iter_content(chunk_size=1024*1024):
                tmp_file.write(chunk)
            tmp_file.flush()
            tmp_file.seek(0)
            return upload_file(tmp_file.name, name, file_type, env)


def upload_file(file_path, name=None, file_type=None, env="STAGE"):
    """Uploads a file to an S3 bucket and returns the file URL."""

    if file_path.startswith('http://') or file_path.startswith('https://'):
        return upload_file_from_url(file_path, name, file_type, env)
    
    with open(file_path, 'rb') as file:
        buffer = file.read()

    return upload_buffer(buffer, name, file_type, env)    


def upload_buffer(buffer, name=None, file_type=None, env="STAGE"):
    """Uploads a buffer to an S3 bucket and returns the file URL."""
    
    assert file_type in [None, '.jpg', '.webp', '.png', '.mp3', 'mp4', '.flac', '.wav'], \
        "file_type must be one of ['.jpg', '.webp', '.png', '.mp3', 'mp4', '.flac', '.wav']"

    if isinstance(buffer, Iterator):
        buffer = b"".join(buffer)

    # Get file extension from mimetype
    mime_type = magic.from_buffer(buffer, mime=True)
    originial_file_type = file_extensions.get(mime_type) or mimetypes.guess_extension(mime_type) or f".{mime_type.split('/')[-1]}"
    if not file_type:
        file_type = originial_file_type

    # if it's an image of the wrong type, convert it
    if file_type != originial_file_type and mime_type.startswith('image/'):
        image = Image.open(io.BytesIO(buffer))
        output = io.BytesIO()
        if file_type == '.jpg':
            image.save(output, 'JPEG', quality=95)
            mime_type = 'image/jpeg'
        elif file_type == '.webp':
            image.save(output, 'WEBP', quality=95)
            mime_type = 'image/webp'
        elif file_type == '.png':
            image.save(output, 'PNG', quality=95)
            mime_type = 'image/png'
        buffer = output.getvalue()

    # if no name is provided, use sha256 of content
    if not name:
        hasher = hashlib.sha256()
        hasher.update(buffer)
        name = hasher.hexdigest()
    
    # Upload file to S3
    filename = f"{name}{file_type}"
    file_bytes = io.BytesIO(buffer)
    
    bucket_name = s3_buckets[env]

    s3.upload_fileobj(
        file_bytes, 
        bucket_name, 
        filename, 
        ExtraArgs={'ContentType': mime_type, 'ContentDisposition': 'inline'}
    )

    # Generate and return file URL
    file_url = f"https://{bucket_name}.s3.amazonaws.com/{filename}"
    print(f"==> Uploaded: {file_url}")

    return file_url, name


def upload_audio_segment(audio: AudioSegment, env="STAGE"):
    buffer = io.BytesIO()
    audio.export(buffer, format="mp3")
    output = upload_buffer(buffer, env=env)
    return output