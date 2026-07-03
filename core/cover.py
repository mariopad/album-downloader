import requests
from PIL import Image
from io import BytesIO


def get_cover(data):

    mbid = data.get("musicbrainz_release_id")
    if not mbid:
        return None

    url = f"https://coverartarchive.org/release/{mbid}/front-500"

    r = requests.get(url)
    if r.status_code != 200:
        return None

    img = Image.open(BytesIO(r.content)).convert("RGB")
    #img = img.resize((600, 600))

    out = BytesIO()
    img.save(out, format="JPEG", quality=90)

    return out.getvalue()