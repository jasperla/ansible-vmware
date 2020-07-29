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
module: vmware_service
short_description: Manage VMware ESXi services
description:
  - Manage VMware ESXi hypervisor services state and policy.
version_added: 2.4
author: Jasper Lievisse Adriaanse (@jasperla)
notes:
  - Tested on vSphere 6.5
requirements:
  - "python >= 2.6"
  - PyVmomi
options:
  name:
    required: true
    aliases: [service]
    description:
      - Name of the service as indicated by the 'label'.
  state:
    required: true
    description:
      - State of the service.
    choices: [ running, stopped, restarted ]
    default: running
  policy:
    required: true
    aliases: [enabled]
    description:
      - Policy for the service to determine if the service needs to be started
        at boot (C(on)/C(off)) or wether it should be started iff it has open
        firewall ports.
    choices: [ on, off, automatic ]
    default: on
'''

EXAMPLES = '''
# Example vmware_service command from Ansible Playbooks
- name: Manage ESXi ssh service
  local_action:
    module: vmware_option
    hostname: esxi_hostname
    username: root
    password: your_password
    name: 'TSM-SSH'
    state: running
    policy: automatic
'''
try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


def manage_service(module, host_system, name, state, policy):
    changed = False

    host_config_manager = host_system.configManager
    host_service_system = host_config_manager.serviceSystem
    services = host_service_system.serviceInfo.service

    # Make sure the service exists by the given name
    service_lst = [s for s in services if s.key == name]

    if len(service_lst) < 1:
        module.fail_json(msg='Could not find service {0} to manage'.format(name))

    service = service_lst[0]

    # First manage the service state
    if state == 'restarted':
        host_service_system.RestartService(name)
        changed = True
    elif state == 'running' and not service.running:
        host_service_system.StartService(name)
        changed = True
    elif state == 'stopped' and service.running:
        host_service_system.StopService(name)
        changed = True

    # Determine if the service needs to be started at boot.
    if policy != service.policy:
        host_service_system.UpdateServicePolicy(name, policy)
        changed = True

    return changed


def main():

    argument_spec = vmware_argument_spec()
    argument_spec.update(dict(name=dict(aliases=['service'], required=True, type='str'),
                              state=dict(default='running', choices=['running', 'stopped', 'restarted'], type='str'),
                              policy=dict(default='on', aliases=['enabled'], choices=['on', 'off', 'automatic'], type='str')))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    name = module.params['name']
    state = module.params['state']
    policy = module.params['policy']

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        content = connect_to_api(module)
        host = get_all_objs(content, [vim.HostSystem])
        if not host:
            module.fail_json(msg="Unable to locate Physical Host.")
        host_system = host.keys()[0]
        changed = manage_service(module, host_system, name, state, policy)
        module.exit_json(changed=changed)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.vmware import *
from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
