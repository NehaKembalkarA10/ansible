#!/usr/bin/python
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
#

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'network'}


DOCUMENTATION = """
---
module: acos_command
author: "Omkar Telee (@omkartelee)"
short_description: Run commands on remote devices running A10 ACOS
description:
  - Sends arbitrary commands to an ios node and returns the results
    read from the device. This module includes an
    argument that will cause the module to wait for a specific condition
    before returning or timing out if the condition is not met.
  - This module does not support running commands in configuration mode.
    Please use M(acos_config) to configure ACOS devices.
notes:
  - Tested against ACOS 4.1.1-P9
options:
  commands:
    description:
      - List of commands to send to the remote acos device over the
        configured provider. The resulting output from the command
        is returned. If the I(wait_for) argument is provided, the
        module is not returned until the condition is satisfied or
        the number of retries has expired. If a command sent to the
        device requires answering a prompt, it is possible to pass
        a dict containing I(command), I(answer) and I(prompt).
        Common answers are 'y' or "\\r" (carriage return, must be
        double quotes). See examples.
    required: true
  wait_for:
    description:
      - List of conditions to evaluate against the output of the
        command. The task will wait for each condition to be true
        before moving forward. If the conditional is not true
        within the configured number of retries, the task fails.
        See examples.
    aliases: ['waitfor']
  match:
    description:
      - The I(match) argument is used in conjunction with the
        I(wait_for) argument to specify the match policy.  Valid
        values are C(all) or C(any).  If the value is set to C(all)
        then all conditionals in the wait_for must be satisfied.  If
        the value is set to C(any) then only one of the values must be
        satisfied.
    default: all
    choices: ['any', 'all']
  retries:
    description:
      - Specifies the number of retries a command should by tried
        before it is considered failed. The command is run on the
        target device every retry and evaluated against the
        I(wait_for) conditions.
    default: 10
  interval:
    description:
      - Configures the interval in seconds to wait between retries
        of the command. If the command does not pass the specified
        conditions, the interval indicates how long to wait before
        trying the command again.
    default: 1
"""

EXAMPLES = r"""
  tasks:
    - name: run commands that require answering a prompt
      acos_command:
        commands:
          - command: 'reboot'
            prompt: "[yes/no]"
            answer: 'no'

    - name: run commands that require answering a prompt
      acos_command:
        commands:
          - command: 'reload'
            prompt: "[yes/no]"
            answer: 'no'

    - name: run commands that require answering a prompt
      acos_command:
        commands:
          - command: 'reload'
            prompt: "[yes/no]"
            answer: 'no'
        interval: 1

    - name: run show version and check to see if output contains ACOS
      acos_command:
        commands: show version
        wait_for: result[0] contains ACOS
        match: any

    - name: run show version with retries
      acos_command:
        commands: show version
        wait_for: result[0] contains ACOS
        retries: 10

    - name: Run commands from lines
      acos_command:
        commands:
          - command: 'configure'
          - command: 'slb server ok6 10.43.24.17'
          - command: 'exit'
"""

RETURN = """
stdout:
  description: The set of responses from the commands
  returned: always apart from low level errors (such as action plugin)
  type: list
  sample: ['...', '...']
stdout_lines:
  description: The value of stdout split into a list
  returned: always apart from low level errors (such as action plugin)
  type: list
  sample: [['...', '...'], ['...'], ['...']]
failed_conditions:
  description: The list of conditionals that have failed
  returned: failed
  type: list
  sample: ['...', '...']
"""
import time

from ansible.module_utils._text import to_text
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network.common.parsing import Conditional
from ansible.module_utils.network.common.utils import transform_commands
from ansible.module_utils.network.common.utils import to_lines
from ansible.module_utils.network.acos.acos import run_commands
from ansible.module_utils.network.acos.acos import acos_argument_spec


def parse_commands(module, warnings):
    commands = transform_commands(module)

    if module.check_mode:
        for item in list(commands):
            if not item['command'].startswith('show'):
                warnings.append(
                    'Only show commands are supported when using check mode, '
                    'not executing %s' % item['command']
                )
                commands.remove(item)

    return commands


def configuration_to_list(configuration):
    sanitized_config_list = list()
    config_list = configuration[0].split('\n')
    for line in config_list:
        if not line.startswith('!'):
            sanitized_config_list.append(line.strip())
    return sanitized_config_list


def main():
    """main entry point for module execution
    """
    argument_spec = dict(
        commands=dict(type='list', required=True),

        wait_for=dict(type='list', aliases=['waitfor']),
        match=dict(default='all', choices=['all', 'any']),

        retries=dict(default=10, type='int'),
        interval=dict(default=1, type='int')
    )
    argument_spec.update(acos_argument_spec)

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=True)

    warnings = list()
    result = {'changed': True, 'warnings': warnings}
    commands = parse_commands(module, warnings)
    wait_for = module.params['wait_for'] or list()

    try:
        conditionals = [Conditional(c) for c in wait_for]
    except AttributeError as exc:
        module.fail_json(msg=to_text(exc))

    retries = module.params['retries']
    interval = module.params['interval']
    match = module.params['match']

    before_config_list = configuration_to_list(run_commands(module,
                                               'show running-config'))

    while retries > 0:
        responses = run_commands(module, commands)
        for item in list(conditionals):
            if item(responses):
                if match == 'any':
                    conditionals = list()
                    break
                conditionals.remove(item)

        if not conditionals:
            break

        time.sleep(interval)
        retries -= 1
    after_config_list = configuration_to_list(run_commands(module,
                                              'show running-config'))
    diff = list(set(after_config_list)-set(before_config_list))
    if len(diff) != 0:
        result['changed'] = True
    else:
        result['changed'] = False

    if conditionals:
        failed_conditions = [item.raw for item in conditionals]
        msg = 'One or more conditional statements have not been satisfied'
        module.fail_json(msg=msg, failed_conditions=failed_conditions)

    result.update({
        'stdout': responses,
        'stdout_lines': list(to_lines(responses)),
    })

    module.exit_json(**result)


if __name__ == '__main__':
    main()
