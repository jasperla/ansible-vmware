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
module: vmware_advanced_setting
short_description: Manage VMware ESXi advanced settings
description:
  - This module allows for managing various advanced settings on ESXi
    hypervisors. At the moment only setting options in the C(UserVars)
    namespace is supported with long or string values.
version_added: 2.4
author: Jasper Lievisse Adriaanse (@jasperla)
notes:
  - Tested on vSphere 6.5
requirements:
  - "python >= 2.6"
  - PyVmomi
options:
  option:
    required: true
    description:
      - Full name of the option. Both esxcli and API (e.g.
        C(/UsersVars/SuppressShellWarning) and C(UserVars.SuppressShellWarning)
        respectively) notation are supported.
  value:
    required: true
    description:
      - Value to set. In case the API expects a long the value is automatically
        converted.
'''

EXAMPLES = '''
# Example vmware_advanced_setting command from Ansible Playbooks
- name: Configure ESXi advanced settings
  local_action:
    module: vmware_option
    hostname: esxi_hostname
    username: root
    password: your_password
    option: /UserVars/SuppressShellWarning
    value: 1
'''
try:
    from pyVmomi import vim, vmodl, VmomiSupport
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

import re


def apply_setting(module, host_system, option, value):
    changed = False

    host_option_manager = host_system.configManager.advancedOption
    options = host_option_manager.QueryOptions(option)

    # Determine the underlying type to ensure we convert it to the right type
    # before updating.
    value_type = type(options[0].value).__name__

    if value_type == 'long':
        if options[0].value != long(value):
            options[0].value = VmomiSupport.vmodlTypes['long'](value)
            host_option_manager.UpdateOptions(options)
            changed = True
    elif value_type == 'str':
        if options[0].value != value:
            options[0].value = VmomiSupport.vmodlTypes['string'](value)
            host_option_manager.UpdateOptions(options)
            changed = True
    elif value_type == 'bool':
        if options[0].value != value:
            options[0].value = VmomiSupport.vmodlTypes['bool'](value)
            host_option_manager.UpdateOptions(options)
            changed = True
    else:
        module.fail_json(msg='Unhandled value type {0}'.format(value_type))

    return changed


def main():

    argument_spec = vmware_argument_spec()
    argument_spec.update(dict(option=dict(required=True, type='str'),
                              value=dict(required=True, type='str')))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    option = module.params['option']
    value = module.params['value']

    # Translate the esxcli-style option to an API key by replacing all slashes
    # with dots, and remove the first slash.
    option = re.sub(r'^/(.*)', r"\1", option).replace('/', '.')

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        content = connect_to_api(module)
        host = get_all_objs(content, [vim.HostSystem])
        if not host:
            module.fail_json(msg="Unable to locate Physical Host.")
        host_system = host.keys()[0]
        changed = apply_setting(module, host_system, option, value)
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
