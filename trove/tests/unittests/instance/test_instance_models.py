#    Copyright 2014 Rackspace Hosting
#    Copyright 2014 Hewlett-Packard Development Company, L.P.
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
import uuid
from mock import Mock
from testtools import TestCase
from trove.common import cfg
from trove.common import exception
from trove.backup import models as backup_models
from trove.datastore import models as datastore_models
from trove.datastore.models import DBDatastoreVersion
from trove.common.instance import ServiceStatuses
from trove.instance.models import filter_ips
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance.models import SimpleInstance
from trove.instance import models
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import api as task_api
from trove.tests.fakes import nova
from trove.tests.unittests.util import util

CONF = cfg.CONF


class SimpleInstanceTest(TestCase):

    def setUp(self):
        super(SimpleInstanceTest, self).setUp()
        db_info = DBInstance(
            InstanceTasks.BUILDING, name="TestInstance")
        self.instance = SimpleInstance(
            None, db_info, InstanceServiceStatus(
                ServiceStatuses.BUILDING), ds_version=Mock(), ds=Mock())
        db_info.addresses = {"private": [{"addr": "123.123.123.123"}],
                             "internal": [{"addr": "10.123.123.123"}],
                             "public": [{"addr": "15.123.123.123"}]}
        self.orig_conf = CONF.network_label_regex
        self.orig_ip_regex = CONF.ip_regex
        self.orig_black_list_regex = CONF.black_list_regex

    def tearDown(self):
        super(SimpleInstanceTest, self).tearDown()
        CONF.network_label_regex = self.orig_conf
        CONF.ip_start = None

    def test_get_root_on_create(self):
        root_on_create_val = Instance.get_root_on_create(
            'redis')
        self.assertFalse(root_on_create_val)

    def test_filter_ips_white_list(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '^(15.|123.)'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        ip = filter_ips(
            ip, CONF.ip_regex, CONF.black_list_regex)
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_filter_ips_black_list(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '.*'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        ip = filter_ips(
            ip, CONF.ip_regex, CONF.black_list_regex)
        self.assertTrue(len(ip) == 2)
        self.assertTrue('10.123.123.123' not in ip)

    def test_one_network_label(self):
        CONF.network_label_regex = 'public'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(['15.123.123.123'], ip)

    def test_two_network_labels(self):
        CONF.network_label_regex = '^(private|public)$'
        ip = self.instance.get_visible_ip_addresses()
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_all_network_labels(self):
        CONF.network_label_regex = '.*'
        ip = self.instance.get_visible_ip_addresses()
        self.assertTrue(len(ip) == 3)
        self.assertTrue('10.123.123.123' in ip)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)


class CreateInstanceTest(TestCase):

    def setUp(self):
        util.init_db()
        self.context = Mock()
        self.name = "name"
        self.flavor_id = 5
        self.image_id = "UUID"
        self.databases = []
        self.users = []
        self.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='mysql',
        )
        self.datastore_version = (
            datastore_models.DBDatastoreVersion.create(
                id=str(uuid.uuid4()),
                datastore_id=self.datastore.id,
                name="5.5",
                manager="mysql",
                image_id="image_id",
                packages="",
                active=True))
        self.volume_size = 1
        self.az = "az"
        self.nics = None
        self.configuration = None
        self.tenant_id = "UUID"
        self.datastore_version_id = str(uuid.uuid4())

        self.db_info = DBInstance.create(
            name=self.name, flavor_id=self.flavor_id,
            tenant_id=self.tenant_id,
            volume_size=self.volume_size,
            datastore_version_id=
            self.datastore_version.id,
            task_status=InstanceTasks.BUILDING,
            configuration_id=self.configuration
        )

        self.backup_name = "name"
        self.descr = None
        self.backup_state = backup_models.BackupState.COMPLETED
        self.instance_id = self.db_info.id
        self.parent_id = None
        self.deleted = False

        self.backup = backup_models.DBBackup.create(
            name=self.backup_name,
            description=self.descr,
            tenant_id=self.tenant_id,
            state=self.backup_state,
            instance_id=self.instance_id,
            parent_id=self.parent_id,
            datastore_version_id=self.datastore_version.id,
            deleted=False
        )
        self.backup.size = 1.1
        self.backup.save()
        self.backup_id = self.backup.id
        self.orig_client = models.create_nova_client
        models.create_nova_client = nova.fake_create_nova_client
        self.orig_api = task_api.API(self.context).create_instance
        task_api.API(self.context).create_instance = Mock()
        self.run_with_quotas = models.run_with_quotas
        models.run_with_quotas = Mock()
        self.check = backup_models.DBBackup.check_swift_object_exist
        backup_models.DBBackup.check_swift_object_exist = Mock(
            return_value=True)
        super(CreateInstanceTest, self).setUp()

    def tearDown(self):
        self.db_info.delete()
        self.backup.delete()
        self.datastore.delete()
        self.datastore_version.delete()
        models.create_nova_client = self.orig_client
        task_api.API(self.context).create_instance = self.orig_api
        models.run_with_quotas = self.run_with_quotas
        backup_models.DBBackup.check_swift_object_exist = self.context
        self.backup.delete()
        self.db_info.delete()
        super(CreateInstanceTest, self).tearDown()

    def test_exception_on_invalid_backup_size(self):
        exc = self.assertRaises(
            exception.BackupTooLarge, models.Instance.create,
            self.context, self.name, self.flavor_id,
            self.image_id, self.databases, self.users,
            self.datastore, self.datastore_version,
            self.volume_size, self.backup_id,
            self.az, self.nics, self.configuration
        )
        self.assertIn("Backup is too large for "
                      "given flavor or volume.", str(exc))

    def test_can_restore_from_backup_with_almost_equal_size(self):
        #target size equals to "1Gb"
        self.backup.size = 0.99
        self.backup.save()
        instance = models.Instance.create(
            self.context, self.name, self.flavor_id,
            self.image_id, self.databases, self.users,
            self.datastore, self.datastore_version,
            self.volume_size, self.backup_id,
            self.az, self.nics, self.configuration)
        self.assertIsNotNone(instance)


class TestReplication(TestCase):

    def setUp(self):
        util.init_db()
        self.replica_datastore_version = Mock(spec=DBDatastoreVersion)
        self.replica_datastore_version.id = "UUID"
        self.replica_datastore_version.manager = 'mysql'
        self.root_info = DBInstance(
            InstanceTasks.NONE,
            id="Another_instance",
            name="TestInstance",
            datastore_version_id=self.replica_datastore_version.id)
        self.root_info.save()
        self.replica_info = DBInstance(
            InstanceTasks.NONE,
            id="UUID",
            name="TestInstance",
            datastore_version_id=self.replica_datastore_version.id,
            slave_of_id="Another_instance")
        self.replica_info.save()
        self.safe_nova = models.create_nova_client
        models.create_nova_client = nova.fake_create_nova_client

        super(TestReplication, self).setUp()

    def tearDown(self):
        models.create_nova_client = self.safe_nova
        self.replica_info.delete()
        self.root_info.delete()
        super(TestReplication, self).tearDown()

    def test_create_replica_from_replica(self):
        self.assertRaises(exception.Forbidden, Instance.create,
                          None, 'name', 2, "UUID", [], [], None,
                          self.replica_datastore_version, 1,
                          None, slave_of_id=self.replica_info.id)
