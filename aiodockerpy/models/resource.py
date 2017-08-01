from docker.models.resource import Model


class Collection:
    async def prepare_model(self, co_attrs):
        attrs = await co_attrs
        if isinstance(attrs, Model):
            attrs.client = self.client
            attrs.collection = self
            return attrs
        elif isinstance(attrs, dict):
            return self.model(attrs=attrs, client=self.client, collection=self)
        else:
            raise Exception("Can't create %s from %s" %
                            (self.model.__name__, attrs))
