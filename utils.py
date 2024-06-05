import pathlib
import httpx
from tqdm import tqdm


def download_file(url, destination_folder, overwrite=False):
    print(f"downloading {url} to {destination_folder}")
    destination_folder = pathlib.Path(destination_folder)
    destination_folder.mkdir(parents=True, exist_ok=True)
    local_filepath = destination_folder / url.split("/")[-1]

    if local_filepath.exists() and not overwrite:
        print(f"File {local_filepath} already exists. Skipping download.")
        return str(local_filepath)

    with httpx.stream("GET", url, follow_redirects=True) as stream:
        total = int(stream.headers["Content-Length"])
        with open(local_filepath, "wb") as f, tqdm(
            total=total, unit_scale=True, unit_divisor=1024, unit="B"
        ) as progress:
            num_bytes_downloaded = stream.num_bytes_downloaded
            for data in stream.iter_bytes():
                f.write(data)
                progress.update(
                    stream.num_bytes_downloaded - num_bytes_downloaded
                )
                num_bytes_downloaded = stream.num_bytes_downloaded
    return str(local_filepath)
