#!/usr/bin/python 
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: softlayer-vs-credentials
short_description: Retrieves os root password for a given instance
description:
    - Retrieves os root password for a given instance as stored in SoftLayer.
    - Thus if root pass has been changed from os it's most probably not up-to-date.
    - Result could be stored using register keyword in ansible.
    - Username and password could be read like <result_ansible_var>.password and
    - <result_ansible_var>.username

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
    fqdn:
        description:
            - The fully qualified domain name of the instance.
        type: string
        required: true

author: scoss
notes:
    - Instead of supplying api_key and username, .softlayer or env variables
'''

from ansible.module_utils.basic import *
import SoftLayer
import sys
import logging
import time
from softlayer_vs_basic import *

class CredentialsReader(SoftlayerVirtualServerBasic):
    def __init__(self, sl_client, instance_config):
        SoftlayerVirtualServerBasic.__init__(self, sl_client, instance_config)
        self._sl_software_component_service = self.sl_client['SoftLayer_Software_Component']
 
    def read_credentials(self):
        installed_components = self.sl_virtual_guest.getSoftwareComponents(id=self.get_vs_id(True)) 
        os_component = self._find_os_component(installed_components)
        return self.single_result(self._sl_software_component_service.getPasswords(id=os_component["id"]))
    
    def _find_os_component(self, components):
        for comp in components:
            comp_description = self._sl_software_component_service.getSoftwareDescription(id=comp["id"])
            if comp_description["operatingSystem"] == 1:
                return comp;
            else:
                continue
        raise Exception("No operating system component found on instance")
                
def main():
    
    module_helper = AnsibleModule(
        argument_spec = dict(
            SLClientConfig.arg_spec().items() + VSInstanceConfigBasic.arg_spec().items()
        )
    )
    
    sl_client_config = SLClientConfig(module_helper.params)
    sl_client = SoftLayer.Client(username=sl_client_config.sl_username, api_key=sl_client_config.api_key)
    vs = CredentialsReader(sl_client,
                                 VSInstanceConfigBasic(ansible_config=module_helper.params))
    try:
        module_helper.exit_json(changed=False, result=vs.read_credentials())
    except Exception as se:
        module_helper.fail_json(changed=False, msg=str(se))

main()