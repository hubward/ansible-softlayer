import SoftLayer
import sys
import logging
import time

class SoftlayerVirtualServerBasic(object):
    __cached_sl_instance_id = None
    
    def __init__(self, sl_client, instance_config):
        self.sl_vs_manager = SoftLayer.VSManager(sl_client)
        self.sl_client = sl_client
        self.ic = instance_config
        self.sl_virtual_guest = sl_client['Virtual_Guest']

    def get_vs_id(self, cached_id=True):
        if cached_id == True and self.__cached_sl_instance_id is not None:
            return self.__cached_sl_instance_id
        result = self.single_result(
            self.sl_vs_manager.list_instances(
                hostname=self.ic.get_host(),
                domain=self.ic.get_domain(),
                mask="id"))
        if result is None:
            __cached_sl_instance_id = None
            return None
        elif not cached_id:
            self.__cached_sl_instance_id = None
        else:
            self.__cached_sl_instance_id = result.get("id")
        return result.get("id")        
    
    def single_result(self, result_list):
        if len(result_list) == 0:
            return None
        else: return result_list[0]  

    
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

        
class VSInstanceConfigBasic(object):
    def __init__(self, ansible_config=None):
        self.from_ansible_config(ansible_config)
           
    def from_ansible_config(self, ansible_config):
        self.fqdn = ansible_config.get("fqdn")
  
    def get_host(self):
        return self.fqdn.partition(".")[0]
         
    def get_domain(self):
        (hostname, dot, domain) = self.fqdn.partition(".")
        if domain == "":
            return hostname
        else:
            return domain
         
    @staticmethod
    def arg_spec():
        return dict(
            fqdn = dict(type = 'str', required=True),
        )                