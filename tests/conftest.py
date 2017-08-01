import uuid
from aiodockerpy import APIClient, DockerClient
from aiodockerpy.errors import ImageNotFound

import pytest


def _random_name():
    return "aiodocker-" + uuid.uuid4().hex[:7]


@pytest.yield_fixture
def random_name():
    yield _random_name


@pytest.yield_fixture
async def api_client():
    api_client = APIClient()
    yield api_client
    await api_client.close()


@pytest.yield_fixture
async def tmp_container(api_client):
    await api_client.pull("busybox:latest")
    container = await api_client.create_container("busybox:latest",
                                              ["touch", "/test"])
    await api_client.start(container)
    yield container['Id']
    await api_client.remove_container(container, v=True, force=True)


@pytest.yield_fixture
async def tmp_image(api_client, tmp_container):
    image = await api_client.commit(tmp_container)
    yield image['Id']
    try:
        await api_client.remove_image(image, force=True)
    except ImageNotFound:
        pass


@pytest.yield_fixture
async def client():
    client = DockerClient()
    yield client
    await client.close()
