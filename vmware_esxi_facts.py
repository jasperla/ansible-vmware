#!/usr/bin/python

# (c) 2017, Jasper Lievisse Adriaanse <jlievisseadriaanse () bol.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: vmware_esxi_facts
short_description: Gather facts about a hypervisor
description:
  - Gather facts about a VMware ESX hypervisor.
version_added: 2.4
author: Jasper Lievisse Adriaanse (@jasperla)
notes:
  - Tested on vSphere 6.5
requirements:
  - "python >= 2.6"
  - PyVmomi
options:
  types:
    default: all
    choices: [ all, datastore, hardware, network, storage, system ]
    description:
      - Filter on type of facts to retrieve.
extends_documentation_fragment: vmware.documentation
'''

EXAMPLES = '''
# Example vmware_esxi_facts command from Ansible Playbooks
- name: Gather ESXi facts
  local_action:
    module: vmware_esxi_facts:
    hostname: esxi_hostname
    username: root
    password: your_password
    types: network
'''

RETURN = '''
'''

try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

from ansible.module_utils.vmware import *
from ansible.module_utils.basic import *

SUPPORTED_TYPES = ['all', 'hardware', 'network', 'storage', 'datastore', 'system']


class EsxiFacts(object):

    def __init__(self, module, types, host_system):
        self.module = module
        self.types = types
        self.facts = {}
        self.host_system = host_system

    def get_facts(self):
        for type in self.types:
            self.facts[type] = eval('self.get_{}_facts'.format(type))()

        return self.facts

    def get_system_facts(self):
        facts = dict()

        # vim.AboutInfo
        product_info = self.host_system.config.product

        for attr in ['name', 'fullName', 'vendor', 'version', 'build',
                     'localeVersion', 'localeBuild', 'osType', 'productLineId',
                     'apiType', 'apiVersion', 'instanceUuid',
                     'licenseProductName', 'licenseProductVersion']:
            facts[attr] = getattr(product_info, attr)

        return facts

    def get_datastore_facts(self):
        facts = dict()

        # vim.Datastore
        datastores = self.host_system.datastore

        for datastore in datastores:
            # vim.Datastore.Info
            datastore_info = datastore.info

            facts[datastore_info.name] = {}
            for attr in ['url', 'containerId', 'timestamp']:
                facts[datastore_info.name][attr] = getattr(datastore_info, attr)

            for attr in ['freeSpace', 'maxFileSize', 'maxVirtualDiskCapacity']:
                facts[datastore_info.name][attr] = bytes_to_human(getattr(datastore_info, attr))
        return facts

    def get_hardware_facts(self):
        facts = dict()

        # vim.host.Summary.HardwareSummary
        hardware = self.host_system.summary.hardware

        facts['total_memory'] = bytes_to_human(hardware.memorySize)

        for attr in ['vendor', 'model', 'uuid', 'cpuModel', 'cpuMhz',
                     'numCpuPkgs', 'numCpuCores', 'numCpuThreads', 'numNics', 'numHBAs']:
            facts[attr] = getattr(hardware, attr)
        return facts

    def get_network_facts(self):
        facts = dict(pnics={}, vnics={}, portgroups={}, vswitch={}, proxySwitch={})

        # vim.host.NetworkInfo
        network_info = self.host_system.configManager.networkSystem.networkInfo

        # vim.host.PhysicalNic
        for nic in network_info.pnic:
            facts['pnics'][nic.device] = dict(
                driver=nic.driver,
                mac=nic.mac,
                pci=nic.pci,
            )

            # Now, some machines don't set nic.linkSpeed correctly
            try:
                facts['pnics'][nic.device]['speed'] = nic.linkSpeed.speedMb
                facts['pnics'][nic.device]['fullduplex'] = nic.linkSpeed.duplex
            except:
                # Tough luck, but carry on.
                pass

        # vim.host.VirtualNic
        for nic in network_info.vnic:
            facts['vnics'][nic.device] = dict(
                portgroup=nic.portgroup,
                mac=nic.spec.mac,
                mtu=nic.spec.mtu,
                ipv4=dict(
                    address=nic.spec.ip.ipAddress,
                    netmask=nic.spec.ip.subnetMask,
                    dhcp=nic.spec.ip.dhcp,
                )
            )

            try:
                facts['vnics'][nic.device]['ipv6'] = dict(
                    address=nic.spec.ip.ipV6Config.ipV6Address[0].ipAddress,
                    prefix=nic.spec.ip.ipV6Config.ipV6Address[0].prefixLength,
                    autoconf=nic.spec.ip.ipV6Config.autoConfigurationEnabled,
                    dhcp=nic.spec.ip.ipV6Config.dhcpV6Enabled
                )
            except:
                # No IPv6 configured for this host.
                pass

        # vim.host.PortGroup
        for pg in network_info.portgroup:
            facts['portgroups'][pg.key] = dict(
                name=pg.spec.name,
                vlanId=pg.spec.vlanId,
                vswitchName=pg.spec.vswitchName,
            )

        # vim.host.HostProxySwitch
        for psw in network_info.proxySwitch:
            facts['proxySwitch'][psw.key] = {}
            for attr in ['dvsName', 'dvsUuid', 'numPorts', 'numPorts',
                         'configNumPorts', 'numPortsAvailable', 'mtu',
                         'networkReservationSupported']:
                facts['proxySwitch'][psw.key][attr] = getattr(psw, attr)

        # vim.host.VirtualSwitch
        for vsw in network_info.vswitch:
            facts['vswitch'][vsw.key] = {}
            for attr in ['name', 'numPorts', 'numPortsAvailable', 'mtu']:
                facts['vswitch'][vsw.key][attr] = getattr(vsw, attr)

        return facts

    def get_storage_facts(self):
        facts = dict(hba={}, lun={}, multipath={}, systemfile=[], mountinfo={})

        # vim.host.StorageSystem
        facts['systemfile'] = self.host_system.configManager.storageSystem.systemFile

        # vim.host.StorageDeviceInfo
        storage_device_info = self.host_system.configManager.storageSystem.storageDeviceInfo
        for hba in storage_device_info.hostBusAdapter:
            facts['hba'][hba.device] = {}
            for attr in ['key', 'bus', 'status', 'model', 'driver', 'pci']:
                facts['hba'][hba.device][attr] = getattr(hba, attr)

        for lun in storage_device_info.scsiLun:
            facts['lun'][lun.uuid] = {}
            for attr in ['displayName', 'lunType', 'vendor', 'revision', 'scsiLevel']:
                facts['lun'][lun.uuid][attr] = getattr(lun, attr)

        # vim.host.FileSystemVolumeInfo
        filesystem_volume_info = self.host_system.configManager.storageSystem.fileSystemVolumeInfo
        facts['volumeTypeList'] = filesystem_volume_info.volumeTypeList

        for m in filesystem_volume_info.mountInfo:
            facts['mountinfo'][m.volume.name] = {}
            facts['mountinfo'][m.volume.name] = dict(
                capacity=bytes_to_human(m.volume.capacity),
                type=m.volume.type,
                vStorageSupport=m.vStorageSupport,
                path=m.mountInfo.path,
                accessMode=m.mountInfo.accessMode,
                mounted=m.mountInfo.mounted,
                accessible=m.mountInfo.accessible,
            )

            if not m.mountInfo.accessible:
                facts['mountinfo'][m.volume.name]['inaccessibleReason'] = m.mountInfo.inaccessibleReason

        # vim.host.MultipathStateInfo
        multipath_state_info = self.host_system.configManager.storageSystem.multipathStateInfo
        for p in multipath_state_info.path:
            facts['multipath'][p.name] = p.pathState

        return facts


def main():

    argument_spec = vmware_argument_spec()
    argument_spec.update(dict(
            types=dict(default='all', type='str', choices=SUPPORTED_TYPES)))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if module.params['types'] == 'all':
        types = filter(lambda e: e != 'all', SUPPORTED_TYPES)
    else:
        types = [module.params['types']]

    result = {'ansible_facts': {'esxi_facts': {}}}
    result['changed'] = False

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        content = connect_to_api(module)
        host = get_all_objs(content, [vim.HostSystem])
        if not host:
            module.fail_json(msg="Unable to locate Physical Host.")
        host_system = host.keys()[0]

        esxi_facts = EsxiFacts(module, types, host_system)
        result['ansible_facts']['esxi_facts'] = esxi_facts.get_facts()
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))

    module.exit_json(**result)


if __name__ == '__main__':
    main()
