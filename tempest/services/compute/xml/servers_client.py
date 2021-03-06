# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2012 IBM
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import time
import urllib

from lxml import etree

from tempest.common.rest_client import RestClientXML
from tempest import exceptions
from tempest.services.compute.xml.common import Document
from tempest.services.compute.xml.common import Element
from tempest.services.compute.xml.common import Text
from tempest.services.compute.xml.common import xml_to_json
from tempest.services.compute.xml.common import XMLNS_11


LOG = logging.getLogger(__name__)


def _translate_ip_xml_json(ip):
    """
    Convert the address version to int.
    """
    ip = dict(ip)
    version = ip.get('version')
    if version:
        ip['version'] = int(version)
    return ip


def _translate_network_xml_to_json(network):
    return [_translate_ip_xml_json(ip.attrib)
            for ip in network.findall('{%s}ip' % XMLNS_11)]


def _translate_addresses_xml_to_json(xml_addresses):
    return dict((network.attrib['id'], _translate_network_xml_to_json(network))
                for network in xml_addresses.findall('{%s}network' % XMLNS_11))


def _translate_server_xml_to_json(xml_dom):
    """Convert server XML to server JSON.

    The addresses collection does not convert well by the dumb xml_to_json.
    This method does some pre and post-processing to deal with that.

    Translate XML addresses subtree to JSON.

    Having xml_doc similar to
    <api:server  xmlns:api="http://docs.openstack.org/compute/api/v1.1">
        <api:addresses>
            <api:network id="foo_novanetwork">
                <api:ip version="4" addr="192.168.0.4"/>
            </api:network>
            <api:network id="bar_novanetwork">
                <api:ip version="4" addr="10.1.0.4"/>
                <api:ip version="6" addr="2001:0:0:1:2:3:4:5"/>
            </api:network>
        </api:addresses>
    </api:server>

    the _translate_server_xml_to_json(etree.fromstring(xml_doc)) should produce
    something like

    {'addresses': {'bar_novanetwork': [{'addr': '10.1.0.4', 'version': 4},
                                       {'addr': '2001:0:0:1:2:3:4:5',
                                        'version': 6}],
                   'foo_novanetwork': [{'addr': '192.168.0.4', 'version': 4}]}}
    """
    nsmap = {'api': XMLNS_11}
    addresses = xml_dom.xpath('/api:server/api:addresses', namespaces=nsmap)
    if addresses:
        if len(addresses) > 1:
            raise ValueError('Expected only single `addresses` element.')
        json_addresses = _translate_addresses_xml_to_json(addresses[0])
        json = xml_to_json(xml_dom)
        json['addresses'] = json_addresses
    else:
        json = xml_to_json(xml_dom)
    return json


class ServersClientXML(RestClientXML):

    def __init__(self, config, username, password, auth_url, tenant_name=None):
        super(ServersClientXML, self).__init__(config, username, password,
                                               auth_url, tenant_name)
        self.service = self.config.compute.catalog_type

    def _parse_key_value(self, node):
        """Parse <foo key='key'>value</foo> data into {'key': 'value'}."""
        data = {}
        for node in node.getchildren():
            data[node.get('key')] = node.text
        return data

    def _parse_links(self, node, json):
        del json['link']
        json['links'] = []
        for linknode in node.findall('{http://www.w3.org/2005/Atom}link'):
            json['links'].append(xml_to_json(linknode))

    def _parse_server(self, body):
        json = _translate_server_xml_to_json(body)

        if 'metadata' in json and json['metadata']:
            # NOTE(danms): if there was metadata, we need to re-parse
            # that as a special type
            metadata_tag = body.find('{%s}metadata' % XMLNS_11)
            json["metadata"] = self._parse_key_value(metadata_tag)
        if 'link' in json:
            self._parse_links(body, json)
        for sub in ['image', 'flavor']:
            if sub in json and 'link' in json[sub]:
                self._parse_links(body, json[sub])
        return json

    def _parse_xml_virtual_interfaces(self, xml_dom):
        """
        Return server's virtual interfaces XML as JSON.
        """
        data = {"virtual_interfaces": []}
        for iface in xml_dom.getchildren():
            data["virtual_interfaces"].append(
                {"id": iface.get("id"),
                 "mac_address": iface.get("mac_address")})
        return data

    def get_server(self, server_id):
        """Returns the details of an existing server."""
        resp, body = self.get("servers/%s" % str(server_id), self.headers)
        server = self._parse_server(etree.fromstring(body))
        return resp, server

    def delete_server(self, server_id):
        """Deletes the given server."""
        return self.delete("servers/%s" % str(server_id))

    def _parse_array(self, node):
        array = []
        for child in node.getchildren():
            array.append(xml_to_json(child))
        return array

    def list_servers(self, params=None):
        url = 'servers/detail'
        if params:
            url += '?%s' % urllib.urlencode(params)

        resp, body = self.get(url, self.headers)
        servers = self._parse_array(etree.fromstring(body))
        return resp, {"servers": servers}

    def list_servers_with_detail(self, params=None):
        url = 'servers/detail'
        if params:
            url += '?%s' % urllib.urlencode(params)

        resp, body = self.get(url, self.headers)
        servers = self._parse_array(etree.fromstring(body))
        return resp, {"servers": servers}

    def update_server(self, server_id, name=None, meta=None, accessIPv4=None,
                      accessIPv6=None):
        doc = Document()
        server = Element("server")
        doc.append(server)

        if name:
            server.add_attr("name", name)
        if accessIPv4:
            server.add_attr("accessIPv4", accessIPv4)
        if accessIPv6:
            server.add_attr("accessIPv6", accessIPv6)
        if meta:
            metadata = Element("metadata")
            server.append(metadata)
            for k, v in meta:
                meta = Element("meta", key=k)
                meta.append(Text(v))
                metadata.append(meta)

        resp, body = self.put('servers/%s' % str(server_id),
                              str(doc), self.headers)
        return resp, xml_to_json(etree.fromstring(body))

    def create_server(self, name, image_ref, flavor_ref, **kwargs):
        """
        Creates an instance of a server.
        name (Required): The name of the server.
        image_ref (Required): Reference to the image used to build the server.
        flavor_ref (Required): The flavor used to build the server.
        Following optional keyword arguments are accepted:
        adminPass: Sets the initial root password.
        key_name: Key name of keypair that was created earlier.
        meta: A dictionary of values to be used as metadata.
        personality: A list of dictionaries for files to be injected into
        the server.
        security_groups: A list of security group dicts.
        networks: A list of network dicts with UUID and fixed_ip.
        user_data: User data for instance.
        availability_zone: Availability zone in which to launch instance.
        accessIPv4: The IPv4 access address for the server.
        accessIPv6: The IPv6 access address for the server.
        min_count: Count of minimum number of instances to launch.
        max_count: Count of maximum number of instances to launch.
        disk_config: Determines if user or admin controls disk configuration.
        """
        server = Element("server",
                         xmlns=XMLNS_11,
                         imageRef=image_ref,
                         flavorRef=flavor_ref,
                         name=name)

        for attr in ["adminPass", "accessIPv4", "accessIPv6", "key_name"]:
            if attr in kwargs:
                server.add_attr(attr, kwargs[attr])

        if 'meta' in kwargs:
            metadata = Element("metadata")
            server.append(metadata)
            for k, v in kwargs['meta'].items():
                meta = Element("meta", key=k)
                meta.append(Text(v))
                metadata.append(meta)

        if 'personality' in kwargs:
            personality = Element('personality')
            server.append(personality)
            for k in kwargs['personality']:
                temp = Element('file', path=k['path'])
                temp.append(Text(k['contents']))
                personality.append(temp)

        resp, body = self.post('servers', str(Document(server)), self.headers)
        server = self._parse_server(etree.fromstring(body))
        return resp, server

    def wait_for_server_status(self, server_id, status):
        """Waits for a server to reach a given status."""
        resp, body = self.get_server(server_id)
        server_status = body['status']
        start = int(time.time())

        while(server_status != status):
            time.sleep(self.build_interval)
            resp, body = self.get_server(server_id)
            server_status = body['status']

            if server_status == 'ERROR':
                raise exceptions.BuildErrorException(server_id=server_id)

            timed_out = int(time.time()) - start >= self.build_timeout

            if server_status != status and timed_out:
                message = ('Server %s failed to reach %s status within the '
                           'required time (%s s).' %
                           (server_id, status, self.build_timeout))
                message += ' Current status: %s.' % server_status
                raise exceptions.TimeoutException(message)

    def wait_for_server_termination(self, server_id, ignore_error=False):
        """Waits for server to reach termination."""
        start_time = int(time.time())
        while True:
            try:
                resp, body = self.get_server(server_id)
            except exceptions.NotFound:
                return

            server_status = body['status']
            if server_status == 'ERROR' and not ignore_error:
                raise exceptions.BuildErrorException

            if int(time.time()) - start_time >= self.build_timeout:
                raise exceptions.TimeoutException

            time.sleep(self.build_interval)

    def _parse_network(self, node):
        addrs = []
        for child in node.getchildren():
            addrs.append({'version': int(child.get('version')),
                         'addr': child.get('version')})
        return {node.get('id'): addrs}

    def list_addresses(self, server_id):
        """Lists all addresses for a server."""
        resp, body = self.get("servers/%s/ips" % str(server_id), self.headers)

        networks = {}
        for child in etree.fromstring(body.getchildren()):
            network = self._parse_network(child)
            networks.update(**network)

        return resp, networks

    def list_addresses_by_network(self, server_id, network_id):
        """Lists all addresses of a specific network type for a server."""
        resp, body = self.get("servers/%s/ips/%s" % (str(server_id),
                                                     network_id),
                              self.headers)
        network = self._parse_network(etree.fromstring(body))

        return resp, network

    def action(self, server_id, action_name, response_key, **kwargs):
        if 'xmlns' not in kwargs:
            kwargs['xmlns'] = XMLNS_11
        doc = Document((Element(action_name, **kwargs)))
        resp, body = self.post("servers/%s/action" % server_id,
                               str(doc), self.headers)
        if response_key is not None:
            body = xml_to_json(etree.fromstring(body))
        return resp, body

    def change_password(self, server_id, password):
        return self.action(server_id, "changePassword", None,
                           adminPass=password)

    def reboot(self, server_id, reboot_type):
        return self.action(server_id, "reboot", None, type=reboot_type)

    def rebuild(self, server_id, image_ref, **kwargs):
        kwargs['imageRef'] = image_ref
        if 'xmlns' not in kwargs:
            kwargs['xmlns'] = XMLNS_11

        attrs = kwargs.copy()
        if 'metadata' in attrs:
            del attrs['metadata']
        rebuild = Element("rebuild",
                          **attrs)

        if 'metadata' in kwargs:
            metadata = Element("metadata")
            rebuild.append(metadata)
            for k, v in kwargs['metadata'].items():
                meta = Element("meta", key=k)
                meta.append(Text(v))
                metadata.append(meta)

        resp, body = self.post('servers/%s/action' % server_id,
                               str(Document(rebuild)), self.headers)
        server = self._parse_server(etree.fromstring(body))
        return resp, server

    def resize(self, server_id, flavor_ref, **kwargs):
        if 'disk_config' in kwargs:
            raise NotImplementedError("Sorry, disk_config not "
                                      "supported via XML yet")
        kwargs['flavorRef'] = flavor_ref
        return self.action(server_id, 'resize', None, **kwargs)

    def confirm_resize(self, server_id, **kwargs):
        return self.action(server_id, 'confirmResize', None, **kwargs)

    def revert_resize(self, server_id, **kwargs):
        return self.action(server_id, 'revertResize', None, **kwargs)

    def create_image(self, server_id, name):
        return self.action(server_id, 'createImage', None, name=name)

    def add_security_group(self, server_id, name):
        return self.action(server_id, 'addSecurityGroup', None, name=name)

    def remove_security_group(self, server_id, name):
        return self.action(server_id, 'removeSecurityGroup', None, name=name)

    def get_console_output(self, server_id, length):
        return self.action(server_id, 'os-getConsoleOutput', 'output',
                           length=length)

    def list_virtual_interfaces(self, server_id):
        """
        List the virtual interfaces used in an instance.
        """
        resp, body = self.get('/'.join(['servers', server_id,
                              'os-virtual-interfaces']), self.headers)
        virt_int = self._parse_xml_virtual_interfaces(etree.fromstring(body))
        return resp, virt_int
