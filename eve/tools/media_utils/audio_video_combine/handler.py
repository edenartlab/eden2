import sys
sys.path.append("../../..")

import tempfile
import subprocess
import eden_utils


async def audio_video_combine(args: dict, _: str = None, env: str = None):
    video_url = args.get("video")
    audio_url = args.get("audio")

    video_file = eden_utils.get_file_handler(".mp4", video_url)
    output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)

    if audio_url:
        audio_file = eden_utils.get_file_handler(".mp3", audio_url)
        audio_duration = eden_utils.get_media_duration(audio_file)

        # loop the video to match the audio duration
        looped_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "panic", "-stream_loop", "-1", 
            "-i", video_file,
            "-c", "copy", "-t", str(audio_duration),
            looped_video.name,
        ]
        subprocess.run(cmd)

        # merge the audio and the looped video
        cmd = [
            "ffmpeg", "-y", "-loglevel", "panic",
            "-i", looped_video.name, "-i", audio_file,
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", "-shortest",
            output_file.name,
        ]

    else:
        # if no audio, create a silent audio track with same duration as video
        video_duration = eden_utils.get_media_duration(video_file)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "panic",
            "-i", video_file,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={video_duration}",
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental",
            output_file.name,
        ]

    subprocess.run(cmd)

    return [output_file.name]
    