import asyncio
import uuid
from aiodockerpy import APIClient
from aiodockerpy.errors import ImageNotFound
from docker.utils import kwargs_from_env
from os import environ as ENV

import pytest


_api_versions = {
    "17.06": "1.30",
    "17.05": "1.29",
    "17.04": "1.28",
    "17.03": "1.27",
}


def _random_name():
    return "aiodocker-" + uuid.uuid4().hex[:7]


@pytest.yield_fixture
def random_name():
    yield _random_name


@pytest.yield_fixture(scope="session")
def base_images():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_pull_base_images())
    yield


async def _pull_base_images():
    kwargs = kwargs_from_env()
    api_client = APIClient(**kwargs)
    try:
        await api_client.pull("busybox:latest")
    finally:
        await api_client.close()


@pytest.yield_fixture(scope="session")
def api_client_kwargs():
    kwargs = kwargs_from_env()
    kwargs['version'] = _api_versions.get(ENV.get("DOCKER_VERSION"))
    kwargs['timeout'] = 5
    loop = asyncio.get_event_loop()
    if "DOCKER_VERSION" in ENV:
        loop.run_until_complete(_ensure_api_version(kwargs))
    yield kwargs


async def _ensure_api_version(kwargs):
    api_client = APIClient(**kwargs)
    try:
        resp = await api_client.version(api_version=False)
        assert resp["ApiVersion"] == api_client.api_version
    finally:
        await api_client.close()


@pytest.yield_fixture
async def api_client(api_client_kwargs):
    api_client = APIClient(**api_client_kwargs)
    yield api_client
    await api_client.close()


@pytest.yield_fixture
async def tmp_container(api_client, base_images):
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
