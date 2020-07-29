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
module: vmware_datetime_config
short_description: Manage VMware ESXi NTP and timezone configuration
description:
  - Manage NTP servers, ntpd service state and timezone settings on
    VMware ESXi hypervisors.
version_added: 2.4
author: Jasper Lievisse Adriaanse (@jasperla)
notes:
  - Tested on vSphere 6.5
requirements:
  - "python >= 2.6"
  - PyVmomi
options:
  ntp_servers:
    required: false
    description:
      - List of NTP servers that should be configured.
  ntpd_state:
    required: false
    description:
      - State of the ntpd service.
    choices: [ running, stopped, restarted ]
    default: running
  timezone:
    required: false
    description:
      - Name of the timezone to use.
extends_documentation_fragment: vmware.documentation
'''

EXAMPLES = '''
# Example vmware_datetime_config command from Ansible Playbooks
- name: Configure ESXi timezone and NTP servers
  local_action:
    module: vmware_datetime_config
    hostname: esxi_hostname
    username: root
    password: your_password
    ntp_servers:
        - ntp-001.example.com
        - ntp-002.example.com
    ntpd_state: running
    timezone: UTC
'''
try:
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


def configure_datetime(module, host_system, ntp_servers, ntpd_state, timezone):
    changed = False
    host_config_manager = host_system.configManager
    host_datetime_system = host_config_manager.dateTimeSystem

    # Configure NTP servers
    current_ntp_servers = host_datetime_system.dateTimeInfo.ntpConfig.server
    if current_ntp_servers != ntp_servers:
        ntpConfig = vim.HostNtpConfig(server=ntp_servers)
        dateConfig = vim.HostDateTimeConfig(ntpConfig=ntpConfig)
        host_datetime_system.UpdateDateTimeConfig(config=dateConfig)
        # Explicitly not restarting the service to give the user full control
        # over when it happens (with handlers).
        changed = True

    # Manage the NTP service
    host_service_system = host_config_manager.serviceSystem
    services = host_service_system.serviceInfo.service

    ntpd_service = [service for service in services if service.key == 'ntpd'][0]

    if ntpd_state == 'restarted':
        host_service_system.RestartService('ntpd')
        changed = True
    elif ntpd_state == 'running' and not ntpd_service.running:
        host_service_system.StartService('ntpd')
        changed = True
    elif ntpd_state == 'stopped' and ntpd_service.running:
        host_service_system.StopService('ntpd')
        changed = True

    # Configure the timezone (making sure the requested timezone
    # is listed as a valid option).
    current_timezone = host_datetime_system.dateTimeInfo.timeZone
    if timezone and (current_timezone.name != timezone):
        timezones = host_datetime_system.QueryAvailableTimeZones()

        if len(list(filter(lambda t: t.name == timezone, timezones))) < 1:
            module.fail_json(msg='Invalid timezone requested')

        dateConfig = vim.HostDataTimeConfig(timeZone=timezone)
        host_datetime_system.UpdateDateTimeConfig(config=dateConfig)
        changed = True

    return changed


def main():

    argument_spec = vmware_argument_spec()
    argument_spec.update(dict(ntp_servers=dict(required=True, type='list'),
                              ntpd_state=dict(default='running', choices=['running', 'stopped', 'restarted'], type='str'),
                              timezone=dict(type='str')))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    ntp_servers = module.params['ntp_servers']
    ntpd_state = module.params['ntpd_state']
    timezone = module.params['timezone']

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        content = connect_to_api(module)
        host = get_all_objs(content, [vim.HostSystem])
        if not host:
            module.fail_json(msg="Unable to locate Physical Host.")
        host_system = host.keys()[0]
        changed = configure_datetime(module, host_system, ntp_servers, ntpd_state, timezone)
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
