import aiohttp
from docker import auth
import docker.client
from docker.tls import TLSConfig
from docker.utils import update_headers, utils
from docker.constants import (
    DEFAULT_TIMEOUT_SECONDS, DEFAULT_USER_AGENT, IS_WINDOWS_PLATFORM,
    DEFAULT_DOCKER_API_VERSION, STREAM_HEADER_SIZE_BYTES, DEFAULT_NUM_POOLS,
    MINIMUM_DOCKER_API_VERSION
)
from functools import partial
import io
import ssl
import struct
import warnings

from ..errors import (
    DockerException, TLSParameterError,
    create_api_error_from_http_exception
)
from ..utils.json_stream import json_stream

import six

# Network
from ..utils import check_resource, minimum_version


class APIClient(
        aiohttp.ClientSession,
        docker.api.client.BuildApiMixin,
        docker.api.client.ContainerApiMixin,
        docker.api.client.DaemonApiMixin,
        docker.api.client.ExecApiMixin,
        docker.api.client.ImageApiMixin,
        docker.api.client.NetworkApiMixin,
        docker.api.client.PluginApiMixin,
        docker.api.client.SecretApiMixin,
        docker.api.client.ServiceApiMixin,
        docker.api.client.SwarmApiMixin,
        docker.api.client.VolumeApiMixin):
    """
    A low-level client for the Docker Engine API.

    Example:

        >>> import docker
        >>> client = docker.APIClient(base_url='unix://var/run/docker.sock')
        >>> client.version()
        {u'ApiVersion': u'1.24',
         u'Arch': u'amd64',
         u'BuildTime': u'2016-09-27T23:38:15.810178467+00:00',
         u'Experimental': True,
         u'GitCommit': u'45bed2c',
         u'GoVersion': u'go1.6.3',
         u'KernelVersion': u'4.4.22-moby',
         u'Os': u'linux',
         u'Version': u'1.12.2-rc1'}

    Args:
        base_url (str): URL to the Docker server. For example,
            ``unix:///var/run/docker.sock`` or ``tcp://127.0.0.1:1234``.
        version (str): The version of the API to use. Set to ``auto`` to
            automatically detect the server's version. Default: ``1.24``
        timeout (int): Default timeout for API calls, in seconds.
        tls (bool or :py:class:`~docker.tls.TLSConfig`): Enable TLS. Pass
            ``True`` to enable it with default options, or pass a
            :py:class:`~docker.tls.TLSConfig` object to use custom
            configuration.
        user_agent (str): Set a custom user agent for requests to the server.
    """
    def __init__(self, base_url=None, version=None,
                 timeout=DEFAULT_TIMEOUT_SECONDS, tls=False,
                 user_agent=DEFAULT_USER_AGENT, num_pools=DEFAULT_NUM_POOLS,
                 loop=None):
        if tls and not base_url:
            raise TLSParameterError(
                'If using TLS, the base_url argument must be provided.'
            )

        self.base_url = base_url
        self.timeout = timeout
        headers = {}
        headers['User-Agent'] = user_agent

        self._auth_configs = auth.load_config()

        base_url = utils.parse_host(
            base_url, IS_WINDOWS_PLATFORM, tls=bool(tls)
        )
        if base_url.startswith('http+unix://'):
            connector = aiohttp.UnixConnector(
                path=base_url[11:], limit=num_pools, loop=loop)
            self.base_url = 'http+docker://localunixsocket'
        elif base_url.startswith('npipe://'):
            raise NotImplementedError("npipe:// connection not implemented")
        else:
            if not isinstance(tls, TLSConfig):
                connector = aiohttp.TCPConnector(limit=num_pools, loop=loop)
            else:
                if not tls.verify:
                    connector = aiohttp.TCPConnector(
                        limit=num_pools, loop=loop, verify_ssl=False)
                else:
                    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
                    ssl_context.load_verify_locations(cafile=tls.ca_cert)
                    ssl_context.load_cert_chain(tls.cert[0],
                                                keyfile=tls.cert[1])
                    connector = aiohttp.TCPConnector(
                        limit=num_pools, loop=loop, ssl_context=ssl_context)
            self.base_url = base_url

        super(APIClient, self).__init__(
            loop=loop, headers=headers, connector=connector)

        # version detection needs to be after unix adapter mounting
        if version is None:
            self._version = DEFAULT_DOCKER_API_VERSION
        elif isinstance(version, six.string_types):
            if version.lower() == 'auto':
                self._version = self._retrieve_server_version()
            else:
                self._version = version
        else:
            raise DockerException(
                'Version parameter must be a string or None. Found {0}'.format(
                    type(version).__name__
                )
            )
        if utils.compare_version('1.6', self._version) < 0:
            raise NotImplementedError("Stream logs from API < 1.6")
        if utils.version_lt(self._version, MINIMUM_DOCKER_API_VERSION):
            warnings.warn(
                'The minimum API version supported is {}, but you are using '
                'version {}. It is recommended you either upgrade Docker '
                'Engine or use an older version of Docker SDK for '
                'Python.'.format(MINIMUM_DOCKER_API_VERSION, self._version)
            )

    def _url(self, pathfmt, *args, **kwargs):
        for arg in args:
            if not isinstance(arg, six.string_types):
                raise ValueError(
                    'Expected a string but found {0} ({1}) '
                    'instead'.format(arg, type(arg))
                )

        quote_f = partial(six.moves.urllib.parse.quote_plus, safe="/:")
        args = map(quote_f, args)

        if kwargs.get('versioned_api', True):
            return '{0}/v{1}{2}'.format(
                self.base_url, self._version, pathfmt.format(*args)
            )
        else:
            return '{0}{1}'.format(self.base_url, pathfmt.format(*args))

    def _render_param(self, param):
        if isinstance(param, bool):
            return ("true" if param else "false")
        elif isinstance(param, (str, int)):
            return param
        else:
            raise NotImplementedError(
                "Unknown param type %r: %r", type(param), param)

    def _clean_params(self, params):
        if params is None:
            return None
        else:
            return {
                k: self._render_param(v)
                for k, v in params.items()
                if v is not None
            }

    def get(self, url, params=None, stream=None, timeout=None):
        if stream:
            timeout = None
        return super(APIClient, self)\
            .get(url, params=self._clean_params(params), timeout=timeout)

    def put(self, *args, **kwargs):
        raise RuntimeError("TODO")

    def delete(self, url, params=None, timeout=None):
        return super(APIClient, self)\
            .delete(url, params=self._clean_params(params),
                    timeout=self.timeout)

    def _set_request_timeout(self, kwargs):
        """Prepare the kwargs for an HTTP request by inserting the timeout
        parameter, if not already present."""
        kwargs.setdefault('timeout', self.timeout)
        return kwargs

    @update_headers
    def _post(self, url, **kwargs):
        return self.post(url, **self._set_request_timeout(kwargs))

    @update_headers
    def _post_json(self, url, data=None, **kwargs):
        return self.post(url, json=data, **self._set_request_timeout(kwargs))

    @update_headers
    def _get(self, url, **kwargs):
        return self.get(url, **self._set_request_timeout(kwargs))

    @update_headers
    def _put(self, url, **kwargs):
        return self.put(url, **self._set_request_timeout(kwargs))

    @update_headers
    def _delete(self, url, **kwargs):
        return self.delete(url, **self._set_request_timeout(kwargs))

    # NOTE: this method name is suffixed with the module name to avoid conflict
    #       with the attribute _raise_for_status in aiohttp.ClientSession
    async def _raise_for_status_aiodockerpy(self, response):
        try:
            response.raise_for_status()
        except aiohttp.client.ClientResponseError as e:
            raise await create_api_error_from_http_exception(e, response)

    async def _result(self, async_response, json=False, binary=False):
        assert not (json and binary)

        async with async_response as response:
            await self._raise_for_status_aiodockerpy(response)
            if json:
                return await response.json()
            if binary:
                return await response.read()
            return await response.text()

    async def _stream_helper(self, async_response, decode=False):
        """Generator for data coming from a chunked-encoded HTTP response."""

        if decode:
            async for chunk in json_stream(
                    self._stream_helper(async_response, False)):
                yield chunk
        else:
            async with async_response as response:
                reader = response.content
                while True:
                    # this read call will block until we get a chunk
                    data = await reader.read(1)
                    if not data:
                        break
                    data += await reader.read(io.DEFAULT_BUFFER_SIZE)
                    yield data

    async def _multiplexed_buffer_helper(self, async_response):
        buf = await self._result(async_response, binary=True)
        buf_length = len(buf)
        walker = 0
        while True:
            if buf_length - walker < STREAM_HEADER_SIZE_BYTES:
                break
            header = buf[walker:walker + STREAM_HEADER_SIZE_BYTES]
            _, length = struct.unpack_from('>BxxxL', header)
            start = walker + STREAM_HEADER_SIZE_BYTES
            end = start + length
            walker = end
            yield buf[start:end]

    async def _multiplexed_response_stream_helper(self, async_response):
        async with async_response as response:
            await self._raise_for_status_aiodockerpy(response)
            reader = response.content
            while True:
                header = await reader.read(STREAM_HEADER_SIZE_BYTES)
                if not header:
                    break
                _, length = struct.unpack('>BxxxL', header)
                if not length:
                    continue
                data = await reader.read(length)
                if not data:
                    break
                yield data

    async def _stream_raw_result(self, async_response):
        ''' Stream result for TTY-enabled container above API 1.6 '''
        async with async_response as response:
            await self._raise_for_status_aiodockerpy(response)
            async for out in response.content.iter_chunked(1):
                yield out.decode()

    async def _get_result(self, container, stream, async_response):
        cont = await self.inspect_container(container)
        return await self._get_result_tty(
            stream, async_response, cont['Config']['Tty'])

    async def _get_result_tty(self, stream, async_response, is_tty):
        # We should also use raw streaming (without keep-alives)
        # if we're dealing with a tty-enabled container.
        if is_tty:
            return self._stream_raw_result(async_response) if stream else \
                await self._result(async_response, binary=True)

        sep = six.binary_type()
        if stream:
            return self._multiplexed_response_stream_helper(async_response)
        else:
            return sep.join([
                x
                async for x in self._multiplexed_buffer_helper(async_response)
            ])

    # container.py

    @check_resource
    async def restart(self, container, timeout=10):
        """
        Restart a container. Similar to the ``docker restart`` command.

        Args:
            container (str or dict): The container to restart. If a dict, the
                ``Id`` key is used.
            timeout (int): Number of seconds to try to stop for before killing
                the container. Once killed it will then be restarted. Default
                is 10 seconds.

        Raises:
            :py:class:`docker.errors.APIError`
                If the server returns an error.
        """
        params = {'t': timeout}
        url = self._url("/containers/{0}/restart", container)
        async with self._post(url, params=params) as res:
            await self._raise_for_status_aiodockerpy(res)

    # network.py

    @minimum_version('1.21')
    async def remove_network(self, net_id):
        """
        Remove a network. Similar to the ``docker network rm`` command.

        Args:
            net_id (str): The network's id
        """
        url = self._url("/networks/{0}", net_id)
        async with self._delete(url) as res:
            await self._raise_for_status_aiodockerpy(res)

    @check_resource
    @minimum_version('1.21')
    async def connect_container_to_network(self, container, net_id,
                                           ipv4_address=None,
                                           ipv6_address=None,
                                           aliases=None, links=None,
                                           link_local_ips=None):
        """
        Connect a container to a network.

        Args:
            container (str): container-id/name to be connected to the network
            net_id (str): network id
            aliases (:py:class:`list`): A list of aliases for this endpoint.
                Names in that list can be used within the network to reach the
                container. Defaults to ``None``.
            links (:py:class:`list`): A list of links for this endpoint.
                Containers declared in this list will be linked to this
                container. Defaults to ``None``.
            ipv4_address (str): The IP address of this container on the
                network, using the IPv4 protocol. Defaults to ``None``.
            ipv6_address (str): The IP address of this container on the
                network, using the IPv6 protocol. Defaults to ``None``.
            link_local_ips (:py:class:`list`): A list of link-local
            (IPv4/IPv6) addresses.
        """
        data = {
            "Container": container,
            "EndpointConfig": self.create_endpoint_config(
                aliases=aliases, links=links, ipv4_address=ipv4_address,
                ipv6_address=ipv6_address, link_local_ips=link_local_ips
            ),
        }

        url = self._url("/networks/{0}/connect", net_id)
        async with self._post_json(url, data=data) as res:
            await self._raise_for_status_aiodockerpy(res)

    # image.py

    @check_resource('image')
    async def remove_image(self, image, force=False, noprune=False):
        """
        Remove an image. Similar to the ``docker rmi`` command.

        Args:
            image (str): The image to remove
            force (bool): Force removal of the image
            noprune (bool): Do not delete untagged parents
        """
        params = {'force': force, 'noprune': noprune}
        async with self._delete(self._url("/images/{0}", image),
                                params=params) as res:
            await self._raise_for_status_aiodockerpy(res)
