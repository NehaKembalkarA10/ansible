#
# (c) 2019 Red Hat Inc.
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
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
---
author: Ansible Networking Team
cliconf: acos
short_description: Use ios cliconf to run command on Cisco IOS platform
description:
  - This ios plugin provides low level abstraction apis for
    sending and receiving CLI commands from Cisco IOS network devices.
"""

import re
import time
import json

from itertools import chain

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils._text import to_text
from ansible.module_utils.common._collections_compat import Mapping
from ansible.module_utils.six import iteritems
from ansible.module_utils.network.common.config import NetworkConfig, dumps
from ansible.module_utils.network.common.utils import to_list
from ansible.plugins.cliconf import CliconfBase, enable_mode


class Cliconf(CliconfBase):

    @enable_mode
    def get_config(self, source='running', flags=None, format=None):
        if source not in ('running', 'startup'):
            raise ValueError(
                "fetching configuration from %s is not supported" % source)

        if format:
            raise ValueError(
                "'format' value %s is not supported for get_config" % format)

        if not flags:
            flags = []
        if source == 'running':
            cmd = 'show running-config '
        else:
            cmd = 'show startup-config '

        cmd += ' '.join(to_list(flags))
        cmd = cmd.strip()

        return self.send_command(cmd)

    @enable_mode
    def edit_config(self, candidate=None, commit=True,
                    replace=None, comment=None):
        resp = {}
        operations = self.get_device_operations()
        self.check_edit_config_capability(operations, candidate,
                                          commit, replace, comment)

        results = []
        requests = []
        if commit:
            self.send_command(command='configure terminal',
                              prompt='(yes/no)', answer="yes")
            for line in to_list(candidate):
                if not isinstance(line, Mapping):
                    line = {'command': line}

                cmd = line['command']
                if cmd != 'end' and cmd[0] != '!':
                    results.append(self.send_command(**line))
                    requests.append(cmd)

            self.send_command('end')
        else:
            raise ValueError('check mode is not supported')

        resp['request'] = requests
        resp['response'] = results
        return resp

    def get(self, command=None, prompt=None, answer=None, sendonly=False,
            output=None, newline=True, check_all=False):
        if not command:
            raise ValueError('must provide value of command to execute')
        if output:
            raise ValueError(
                "'output' value %s is not supported for get" % output)

        return self.send_command(command=command, prompt=prompt, answer=answer,
                                 sendonly=sendonly, newline=newline,
                                 check_all=check_all)

    def get_device_info(self):
        device_info = {}

        device_info['network_os'] = 'acos'
        reply = self.get(command='show version')
        data = to_text(reply, errors='surrogate_or_strict').strip()

        match = re.search(r'Version (\S+)', data)
        if match:
            device_info['network_os_version'] = match.group(1).strip(',')

        model_search_strs = [
            r'^ACOS (.+) \(revision', r'^[Cc]isco (\S+).+bytes of .*memory']
        for item in model_search_strs:
            match = re.search(item, data, re.M)
            if match:
                version = match.group(1).split(' ')
                device_info['network_os_model'] = version[0]
                break

        match = re.search(r'^(.+) uptime', data, re.M)
        if match:
            device_info['network_os_hostname'] = match.group(1)

        match = re.search(r'image file is "(.+)"', data)
        if match:
            device_info['network_os_image'] = match.group(1)

        return device_info

    def get_device_operations(self):
        return {
            'supports_diff_replace': True,
            'supports_commit': False,
            'supports_rollback': False,
            'supports_defaults': True,
            'supports_onbox_diff': False,
            'supports_commit_comment': False,
            'supports_multiline_delimiter': True,
            'supports_diff_match': True,
            'supports_diff_ignore_lines': True,
            'supports_generate_diff': True,
            'supports_replace': False
        }

    def get_option_values(self):
        return {
            'format': ['text'],
            'diff_match': ['line', 'strict', 'exact', 'none'],
            'diff_replace': ['line', 'block'],
            'output': []
        }

    def get_capabilities(self):
        result = super(Cliconf, self).get_capabilities()
        result['rpc'] += ['edit_banner', 'get_diff', 'run_commands',
                          'get_defaults_flag']
        result['device_operations'] = self.get_device_operations()
        result.update(self.get_option_values())
        return json.dumps(result)

    def run_commands(self, commands=None, check_rc=True):
        if commands is None:
            raise ValueError("'commands' value is required")

        responses = list()
        for cmd in to_list(commands):
            if not isinstance(cmd, Mapping):
                cmd = {'command': cmd}

            output = cmd.pop('output', None)
            if output:
                raise ValueError("'output' value %s is not supported for"
                                 "run_commands" % output)

            try:
                out = self.send_command(**cmd)
            except AnsibleConnectionFailure as e:
                if check_rc:
                    raise
                out = getattr(e, 'err', to_text(e))

            responses.append(out)

        return responses

    def get_defaults_flag(self):
        """
        The method identifies the filter that should be used to fetch
        running-configuration with defaults.
        :return: valid default filter
        """
        out = self.get('show running-config')
        out = to_text(out, errors='surrogate_then_replace')
        return 'with-default'
