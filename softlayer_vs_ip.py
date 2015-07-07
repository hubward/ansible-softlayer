#!/usr/bin/python 
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: softlayer_vs_ip
short_description: Retrieves instance ip addresses from Softlayer
description:
    - Retrieves instance ip addresses of all adapters from Softlayer
    - the result is stored in the "result" dict entry of he registered variable

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

class IpAddressReader(SoftlayerVirtualServerBasic):
    def __init__(self, sl_client, instance_config):
        SoftlayerVirtualServerBasic.__init__(self, sl_client, instance_config)
 
    def read_ip_address(self):
        sl_instance = self.sl_virtual_guest.getObject(id=self.get_vs_id(True), mask='primaryBackendIpAddress, primaryIpAddress')
        return sl_instance

def main():
    
    module_helper = AnsibleModule(
        argument_spec = dict(
            SLClientConfig.arg_spec().items() + VSInstanceConfigBasic.arg_spec().items()
        )
    )
    
    sl_client_config = SLClientConfig(module_helper.params)
    sl_client = SoftLayer.Client(username=sl_client_config.sl_username, api_key=sl_client_config.api_key)
    vs = IpAddressReader(sl_client,
                                 VSInstanceConfigBasic(ansible_config=module_helper.params))
    try:
        module_helper.exit_json(changed=False, result=vs.read_ip_address())
    except Exception as se:
        module_helper.fail_json(changed=False, msg=str(se))

main()