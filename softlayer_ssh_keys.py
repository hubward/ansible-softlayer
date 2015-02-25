#!/usr/bin/python 
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: softlayer-vs
short_description: Maintains a list of SSH Keys in SoftLayer Public Cloud Account
description:
    - Maintains a list of SSH Keys in SoftLayer Public Cloud Account
    - Labels and keys alone needs to be unique along the list
requirements:
    - Requires SoftLayer python client
    - Requires Ansible
options:
    api_key:
        description:
            - SoftLayer API Key
        default: null
    sl_username:
        description:
            - SoftLayer username
        default: null
    keys_to_check_in:
        description:
            - List of ssh key dicts i.e. label:value, key:value
        default: {}
           
author: scoss
notes:
    - Instead of supplying api_key and username, .softlayer or env variables
    - Example:
    - --- 
    - api_key: 311dc0503fa17c8284c0094876dd8b74d605c43354fgd5cf343c7cc5b27005
    - sl_username: user1
    - keys_to_check_in: 
    -  - key: ssh-rsa 121211311414141414...
    -    label: key1
    -  - key: ssh-rsa AAAAB3NzaC1yc2EAAA...
    -    label: key2
'''


from ansible.module_utils.basic import *
import SoftLayer
import sys
import logging
import time

    
class SLClientConfig(object):
    def __init__(self, params):
        self.api_key= params.get("api_key")
        self.sl_username = params.get("sl_username")
    
    @staticmethod
    def arg_spec():
        return dict(
            api_key = dict(type = 'str'),
            sl_username = dict(type = 'str'),
        )
    
class SshKeysConfig(object):
    def __init__(self, ansible_config):
        self.ssh_keys = ansible_config.get("ssh_keys")
        for ssh_key in self.ssh_keys:
            label = ssh_key.get("label")
            key = ssh_key.get("key")
            if label is None or label == "":
                raise ValueError("No label provided for key {}".format(key))
            if key is None or key == "":
                raise ValueError("No key provided for label {}".format(label))
            for ssh_key2 in self.ssh_keys:
                if ssh_key2 is ssh_key:
                    continue
                if ssh_key2["label"] == ssh_key["label"]:
                    raise ValueError("label {} is not unique".format(ssh_key2["label"]))
                if ssh_key2["key"] == ssh_key["key"]:
                    raise ValueError("ssh_key {} is not unique".format(ssh_key2["key"]))
                
    @staticmethod
    def arg_spec():
        return dict(
            ssh_keys = dict(type = 'list')
        )
           
    def sl_keys_to_delete(self, sl_keys):
        return filter(
            lambda sl_ssh_key: self._doesnt_have_key(sl_ssh_key, self.ssh_keys), 
            sl_keys)
    
    def config_keys_to_add(self, sl_keys):
        return filter(
            lambda config_ssh_key: self._doesnt_have_key(config_ssh_key, sl_keys),
            self.ssh_keys)
    
    def _doesnt_have_key(self, key_to_check, keys_list):
        for ssh_key in keys_list    :
            if ssh_key["label"] == key_to_check["label"] and \
                ssh_key["key"] == key_to_check["key"]:
                return False   
        return True

        
class SshKeys(object):
    _mba_note = "maintained by ansible"
    
    def __init__(self, sl_client, keys_config):
        self._sl_ssh_keys_manager = SoftLayer.SshKeyManager(sl_client)
        self._kc = keys_config

    
    def sync_config(self):
        try:
            sl_keys = self._keys_maintained_by_ansible()
            sl_keys_to_delete = self._kc.sl_keys_to_delete(sl_keys)
            for ssh_key in sl_keys_to_delete:
                self._sl_ssh_keys_manager.delete_key(ssh_key["id"])
        
            config_keys_to_add = self._kc.config_keys_to_add(sl_keys)
            for ssh_key in config_keys_to_add:
                self._sl_ssh_keys_manager.add_key(ssh_key["key"], ssh_key["label"], SshKeys._mba_note)
        except Exception as e:
            raise SSHKeyException(str(e))
        return len(sl_keys_to_delete) != 0 or len(config_keys_to_add) != 0
    
    def _keys_maintained_by_ansible(self):
        sl_keys = self._sl_ssh_keys_manager.list_keys()
        return filter(
            lambda ssh_key: True if ssh_key.get("notes") == SshKeys._mba_note else False,
            sl_keys)

class SSHKeyException(Exception):
    def __init__(self, msg):
        self._msg = msg
    def __str__(self):
        return "Exception: {}, MSG: {}".format(type(self), self._msg)
    def msg(self):
        return self._msg
   
def main():
    
    module_helper = AnsibleModule(
        argument_spec = dict(
            SLClientConfig.arg_spec().items() + SshKeysConfig.arg_spec().items()
        )
    )
    
    sl_client_config = SLClientConfig(module_helper.params)
    sl_client = SoftLayer.Client(sl_client_config.sl_username, sl_client_config.api_key)

    try:
        ssh_keys = SshKeys(sl_client, SshKeysConfig(ansible_config=module_helper.params))
        module_helper.exit_json(changed=ssh_keys.sync_config())
    except Exception as se:
        module_helper.fail_json(msg=str(se))

main()









