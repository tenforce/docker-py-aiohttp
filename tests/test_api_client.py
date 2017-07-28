import tarfile
from io import BytesIO

import pytest


@pytest.mark.asyncio
async def test_history(api_client, tmp_image):
    resp = await api_client.history(tmp_image)
    assert len(resp) >= 1


@pytest.mark.asyncio
async def test_inspect_image(api_client, tmp_image):
    resp = await api_client.inspect_image(tmp_image)
    assert resp


@pytest.mark.asyncio
async def test_get_image(api_client, tmp_image):
    resp = await api_client.get_image(tmp_image)
    fh = BytesIO(await resp.read())
    tar = tarfile.open(fileobj=fh)
    assert len(tar.getmembers()) >= 1


@pytest.mark.asyncio
async def test_import_image(api_client, tmp_image, random_name):
    repository = random_name()
    name = "%s:latest" % repository
    resp = await api_client.get_image(tmp_image)
    fh = BytesIO(await resp.read())
    await api_client.import_image(src=fh, repository=repository, tag="latest")
    resp = await api_client.images(name)
    assert len(resp) >= 1
    await api_client.remove_image(name)
    resp = await api_client.images(name)
    assert len(resp) == 0


@pytest.mark.asyncio
async def test_images(api_client, tmp_image):
    images = await api_client.images(all=True)
    res = [x for x in images if x['Id'].startswith(tmp_image)]
    assert len(res) >= 1


@pytest.mark.asyncio
async def test_remove_image(api_client, tmp_image):
    resp = await api_client.get_image(tmp_image)
    await api_client.remove_image(tmp_image)
    images = await api_client.images(all=True)
    res = [x for x in images if x['Id'].startswith(tmp_image)]
    assert len(res) == 0


@pytest.mark.asyncio
async def test_load_image(api_client, tmp_image):
    resp = await api_client.get_image(tmp_image)
    image_bin = await resp.read()
    await api_client.remove_image(tmp_image)
    images = await api_client.images(all=True)
    res = [x for x in images if x['Id'].startswith(tmp_image)]
    assert len(res) == 0
    await api_client.load_image(image_bin)
    images = await api_client.images(all=True)
    res = [x for x in images if x['Id'].startswith(tmp_image)]
    assert len(res) == 1


@pytest.mark.asyncio
async def test_tag(api_client, tmp_image, random_name):
    repository = random_name()
    res = await api_client.tag(tmp_image, repository)
    assert res is True
    images = await api_client.images(repository)
    assert len(images) >= 1
