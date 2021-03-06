# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack, LLC
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

from tempest.common.utils.data_utils import rand_name
from tempest.test import attr
from tempest.tests.compute import base


class ServersTestJSON(base.BaseComputeTest):
    _interface = 'json'

    @classmethod
    def setUpClass(cls):
        super(ServersTestJSON, cls).setUpClass()
        cls.client = cls.servers_client

    @attr(type='positive')
    def test_create_server_with_admin_password(self):
        # If an admin password is provided on server creation, the server's
        # root password should be set to that password.

        try:
            server = None
            name = rand_name('server')
            resp, server = self.create_server_with_extras(name, self.image_ref,
                                                          self.flavor_ref,
                                                          adminPass='test'
                                                          'password')

            #Verify the password is set correctly in the response
            self.assertEqual('testpassword', server['adminPass'])

        #Teardown
        finally:
            if server:
                self.client.delete_server(server['id'])

    def test_create_with_existing_server_name(self):
        # Creating a server with a name that already exists is allowed

        try:
            id1 = None
            id2 = None
            server_name = rand_name('server')
            resp, server = self.create_server_with_extras(server_name,
                                                          self.image_ref,
                                                          self.flavor_ref)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')
            id1 = server['id']
            resp, server = self.create_server_with_extras(server_name,
                                                          self.image_ref,
                                                          self.flavor_ref)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')
            id2 = server['id']
            self.assertNotEqual(id1, id2, "Did not create a new server")
            resp, server = self.client.get_server(id1)
            name1 = server['name']
            resp, server = self.client.get_server(id2)
            name2 = server['name']
            self.assertEqual(name1, name2)
        finally:
            for server_id in (id1, id2):
                if server_id:
                    self.client.delete_server(server_id)

    @attr(type='positive')
    def test_create_specify_keypair(self):
        # Specify a keypair while creating a server

        try:
            server = None
            key_name = rand_name('key')
            resp, keypair = self.keypairs_client.create_keypair(key_name)
            resp, body = self.keypairs_client.list_keypairs()
            server_name = rand_name('server')
            resp, server = self.create_server_with_extras(server_name,
                                                          self.image_ref,
                                                          self.flavor_ref,
                                                          key_name=key_name)
            self.assertEqual('202', resp['status'])
            self.client.wait_for_server_status(server['id'], 'ACTIVE')
            resp, server = self.client.get_server(server['id'])
            self.assertEqual(key_name, server['key_name'])
        finally:
            if server:
                self.client.delete_server(server['id'])

    @attr(type='positive')
    def test_update_server_name(self):
        # The server name should be changed to the the provided value
        try:
            server = None
            name = rand_name('server')
            resp, server = self.create_server_with_extras(name, self.image_ref,
                                                          self.flavor_ref)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')

            #Update the server with a new name
            resp, server = self.client.update_server(server['id'],
                                                     name='newname')
            self.assertEquals(200, resp.status)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')

            #Verify the name of the server has changed
            resp, server = self.client.get_server(server['id'])
            self.assertEqual('newname', server['name'])

        #Teardown
        finally:
            if server:
                self.client.delete_server(server['id'])

    @attr(type='positive')
    def test_update_access_server_address(self):
        # The server's access addresses should reflect the provided values
        try:
            server = None
            name = rand_name('server')
            resp, server = self.create_server_with_extras(name, self.image_ref,
                                                          self.flavor_ref)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')

            #Update the IPv4 and IPv6 access addresses
            resp, body = self.client.update_server(server['id'],
                                                   accessIPv4='1.1.1.1',
                                                   accessIPv6='::babe:202:202')
            self.assertEqual(200, resp.status)
            self.client.wait_for_server_status(server['id'], 'ACTIVE')

            #Verify the access addresses have been updated
            resp, server = self.client.get_server(server['id'])
            self.assertEqual('1.1.1.1', server['accessIPv4'])
            self.assertEqual('::babe:202:202', server['accessIPv6'])

        #Teardown
        finally:
            if server:
                self.client.delete_server(server['id'])

    def test_delete_server_while_in_building_state(self):
        # Delete a server while it's VM state is Building
        name = rand_name('server')
        resp, server = self.create_server_with_extras(name, self.image_ref,
                                                      self.flavor_ref)
        self.client.wait_for_server_status(server['id'], 'BUILD')
        resp, _ = self.client.delete_server(server['id'])
        self.assertEqual('204', resp['status'])


class ServersTestXML(ServersTestJSON):
    _interface = 'xml'
