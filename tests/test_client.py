import tarfile
from docker.models.images import Image
from io import BytesIO

import pytest


@pytest.mark.asyncio
async def test_get_image(client, tmp_image):
    image = await client.images.get(tmp_image)
    assert isinstance(image, Image)
    resp = await image.save()
    fh = BytesIO(await resp.read())
    tar = tarfile.open(fileobj=fh)
    assert len(tar.getmembers()) >= 1


@pytest.mark.asyncio
async def test_tag(client, tmp_image, random_name):
    repository = random_name()
    image = await client.images.get(tmp_image)
    assert isinstance(image, Image)
    res = await image.tag(repository)
    assert res is True
    images = await client.images.list(name=repository)
    assert len(images) >= 1
