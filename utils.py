import pathlib
import httpx
from tqdm import tqdm


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