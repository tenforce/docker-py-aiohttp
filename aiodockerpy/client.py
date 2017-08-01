import docker.client
from aiodockerpy import APIClient
from aiodockerpy.models.resource import Collection


class DockerClient(docker.client.DockerClient):
    collections = {}

    def __init__(self, *args, **kwargs):
        self.api = APIClient(*args, **kwargs)

    async def close(self):
        await self.api.close()

    @property
    def containers(self):
        return self.collections['ContainerCollection'](client=self)

    @property
    def images(self):
        return self.collections['ImageCollection'](client=self)

    @property
    def networks(self):
        return self.collections['NetworkCollection'](client=self)

    @property
    def nodes(self):
        return self.collections['NodeCollection'](client=self)

    @property
    def plugins(self):
        return self.collections['PluginCollection'](client=self)

    @property
    def secrets(self):
        return self.collections['SecretCollection'](client=self)

    @property
    def services(self):
        return self.collections['ServiceCollection'](client=self)

    @property
    def volumes(self):
        return self.collections['VolumeCollection'](client=self)


for collection in [
            'ContainerCollection', 'ImageCollection', 'NetworkCollection',
            'NodeCollection', 'PluginCollection', 'SecretCollection',
            'ServiceCollection', 'VolumeCollection'
        ]:
    cls = getattr(docker.client, collection)
    new_cls = type(collection, (Collection, cls), {})
    DockerClient.collections[collection] = new_cls
