#
# This code is part of Ansible, but is an independent component.
#
# This particular file snippet, and this file snippet only, is BSD licensed.
# Modules you write using this snippet, which is embedded dynamically by
# Ansible still belong to the author of the module, and may assign their
# own license to the complete work.
#
# Copyright: (c) 2019, Red Hat Inc.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import os
import time

from ansible.module_utils._text import to_text
from ansible.module_utils.basic import env_fallback
from ansible.module_utils.network.common.utils import to_list
from ansible.module_utils.connection import Connection, ConnectionError

_DEVICE_CONFIGS = {}

acos_provider_spec = {
    'host': dict(),
    'port': dict(type='int'),
    'username': dict(fallback=(env_fallback, ['ANSIBLE_NET_USERNAME'])),
    'password': dict(fallback=(env_fallback, ['ANSIBLE_NET_PASSWORD']),
                     no_log=True),
    'ssh_keyfile': dict(fallback=(env_fallback, ['ANSIBLE_NET_SSH_KEYFILE']),
                        type='path'),
    'authorize': dict(fallback=(env_fallback, ['ANSIBLE_NET_AUTHORIZE']),
                      type='bool'),
    'auth_pass': dict(fallback=(env_fallback, ['ANSIBLE_NET_AUTH_PASS']),
                      no_log=True),
    'timeout': dict(type='int')
}
acos_argument_spec = {
    'provider': dict(type='dict', options=acos_provider_spec),
}

acos_top_spec = {
    'host': dict(removed_in_version=2.9),
    'port': dict(removed_in_version=2.9, type='int'),
    'username': dict(removed_in_version=2.9),
    'password': dict(removed_in_version=2.9, no_log=True),
    'ssh_keyfile': dict(removed_in_version=2.9, type='path'),
    'authorize': dict(fallback=(env_fallback, ['ANSIBLE_NET_AUTHORIZE']),
                      type='bool'),
    'auth_pass': dict(removed_in_version=2.9, no_log=True),
    'timeout': dict(removed_in_version=2.9, type='int')
}
acos_argument_spec.update(acos_top_spec)


def get_provider_argspec():
    return acos_provider_spec


def get_connection(module):
    if hasattr(module, '_acos_connection'):
        return module._acos_connection

    capabilities = get_capabilities(module)
    network_api = capabilities.get('network_api')
    if network_api == 'cliconf':
        module._acos_connection = Connection(module._socket_path)
    else:
        module.fail_json(msg='Invalid connection type %s' % network_api)

    return module._acos_connection


def get_capabilities(module):
    if hasattr(module, '_acos_capabilities'):
        return module._acos_capabilities
    try:
        capabilities = Connection(module._socket_path).get_capabilities()
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc, errors='surrogate_then_replace'))
    module._acos_capabilities = json.loads(capabilities)
    return module._acos_capabilities


def get_defaults_flag(module):
    connection = get_connection(module)
    try:
        out = connection.get_defaults_flag()
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc, errors='surrogate_then_replace'))
    return to_text(out, errors='surrogate_then_replace').strip()


def get_config(module, flags=None):
    flags = to_list(flags)

    section_filter = False
    if flags and 'section' in flags[-1]:
        section_filter = True

    flag_str = ' '.join(flags)

    try:
        return _DEVICE_CONFIGS[flag_str]
    except KeyError:
        connection = get_connection(module)
        try:
            out = connection.get_config(flags=flags)
        except ConnectionError as exc:
            if section_filter:
                out = get_config(module, flags=flags[:-1])
            else:
                module.fail_json(
                    msg=to_text(
                        exc, errors='surrogate_then_replace'))
        cfg = to_text(out, errors='surrogate_then_replace').strip()
        _DEVICE_CONFIGS[flag_str] = cfg
        return cfg


def run_commands(module, commands, check_rc=True):
    connection = get_connection(module)
    try:
        return connection.run_commands(commands=commands, check_rc=check_rc)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))


def load_config(module, commands):
    connection = get_connection(module)

    try:
        resp = connection.edit_config(commands)
        return resp.get('response')
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))


def backup(module, running_config):
    backup_options = module.params['backup_options']
    backup_path = backup_options['dir_path']
    backup_filename = str(backup_options['filename'])
    module.params['host'] = 'acos'
    if not os.path.exists(backup_path):
        try:
            os.mkdir(backup_path)
        except Exception:
            module.fail_json(
                msg="Can't create directory {0} Permission denied ?"
                .format(backup_path))
    tstamp = time.strftime("%Y-%m-%d@%H:%M:%S", time.localtime(time.time()))
    if backup_filename != 'None':
        filename = '%s/%s' % (backup_path, backup_filename)
    else:
        filename = '%s/%s_config.%s' % (backup_path, module.params['host'],
                                        tstamp)
    try:
        fh = open(filename, 'w+').write(running_config)
    except Exception:
        module.fail_json(msg="Can't create backup file {0} Permission denied ?"
                         .format(filename))
