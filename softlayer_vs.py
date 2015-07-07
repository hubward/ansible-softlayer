#!/usr/bin/python 
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: softlayer-vs
short_description: manages virtual server instance in SoftLayer Public Cloud
description:
    - Creates / deletes a Virtual Server instance in SoftLayer Public Cloud
    - and optionally waits for it to be 'running'.
    - Later editing these fields, requires downtime and very often instance
    - recreation. Individual field descriptions describes what is the impact
    - of changing the value
requirements:
    - Requires SoftLayer python client
    - Requires Ansible
options:
    state:
        description:
            - Indicate desired state of the virtual server
        choices: ['present','running', 'absent']
        default: running
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
            - Fully qualified hostname of the instance. 
        type: string
        required: true
    payment_scheme:
        description:
            - Indicates wether payment is on hourly or monthly basis.
            - Changing the value causes instance recreation
        choices: ['hourly', 'monthly']
        default: 'hourly'
    dedicated:
        description:
            - Indicates whether this instance should be installed on shared
            - hypervisor or not. May occur additional taxes.
            - Changing the value causes instance recreation.
        choices: ['yes', 'no']
        default: false
    datacenter:
        description:
            - The short name of the data center where the server should be run
            - Changing the value causes instance recreation
        type: string
        required: true
    os_code:
        description:
            - The SoftLayer reference code for operation system. For example DEBIAN_7_64
            - Do not use relative codes like DEBIAN_LATEST because these are normalized
            - to a concrete reference code. At the moment of writing DEBIAN_LATES is
            - normalized to DEBIAN_7_64
            - Changing the value causes instance recreation
        type: string
        required: true
    private:
        description:
            - Indicates wether the instance should be attached only to a private network
            - Changing the value causes instance recreation
        choices: ['yes', 'no']
    post_install_script:
        description:
            - The URL of the post install script.
            - Changing the value causes OS reload.
        type: string
        default: null
    
    user_data:
        description:
            - User provided data that will be accessible from the system. Could be used to
            - pass parameters to the post install script. Data is accessible by
            - mounting /dev/xvdh1. Path to raw data is openstack/latest/user_data.
            - If changed nothing will happen. This is basically used the first time
            - a system is created to configure first-time users setup
        type: string
        default: null
    
    root_ssh_keys:
        description:
            - List of SSH keys to be installed for the root.
            - Changing the value causes OS reload.
        default: {}
    nic_spped:
        description:
            - The speed of network interfaces attached to the instance.
            - Changing the value causes instance recreation.
        choice: ["10Mb", "100Mb", "1Gb"]
    CPUs:
        description:
            - The number of CPUs on instance
            - Changing the value causes short downtime ~ 5 mins
        choice: [1, 2, 4]
    RAM:
        description:
            - The amount of memory in GB.
            - Changing the value causes short downtime ~ 5 mins
        choice: ["1GB", "2GB", "4GB", "8GB"]
    wait:
        description:
            - The time in seconds to wait for change transtion
            - i.e. to start, stop, provision, shutdown the instance
            - 0 means do not wait i.e. create instance asynchronously
        type: integer
        default: 600

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

class VSState(object):
    @staticmethod
    def PRESENT(): return "present"
    @staticmethod
    def RUNNING(): return "running"
    @staticmethod
    def ABSENT(): return "absent"

class VSPaymentScheme(object):
    @staticmethod
    def from_sl(sl_hourly):
        if hourly == True:
            return VSPaymentScheme.HOURLY()
        elif sl_hourly == False:
            return VSPaymentScheme.MONTHLY()
        else:
            raise TypeError("boolean i.e. True or False expected")
    
    @staticmethod
    def to_sl(payment_scheme):
        if payment_scheme == VSPaymentScheme.HOURLY():
            return True
        elif payment_scheme == VSPaymentScheme.MONTHLY():
            return False
        elif not type(payment_scheme) is str:
            raise TypeError("String expected")
        else:
            raise ValueError("One of {} or {} expected".format(VSPaymentScheme.HOURLY, VSPaymentScheme.MONTHLY))
    
    @staticmethod
    def HOURLY(): return "hourly"
    @staticmethod
    def MONTHLY(): return "monthly"
    

class NICSpeed(object):
    @staticmethod
    def to_sl(nic_speed):
        if not type(nic_speed) is str:
            raise TypeError("String expected, was {}".format(type(nic_speed)))
        elif nic_speed == NICSpeed.Gb1():
            return 1000
        elif nic_speed == NICSpeed.Mb10():
            return 10
        elif nic_speed == NICSpeed.Mb100():
            return 100
        else:
            raise ValueError("One of {}, {} or {} expected".format(NICSpeed.Gb1, NICSpeed.Mb10, NICSpeed.Mb100))
    
    @staticmethod
    def from_sl(sl_nic_speed):
        if sl_nic_speed == 1000:
            return NICSpeed.Gb1()
        if sl_nic_speed == 100:
            return NICSpeed.Mb100()
        if sl_nic_speed == 10:
            return NICSpeed.Mb10()
        raise ValueError("Unknown nic speed: {}MB".format(sl_nic_speed))
        
    @staticmethod
    def Gb1(): return "1Gb"
    @staticmethod
    def Mb10(): return "10Mb"
    @staticmethod
    def Mb100(): return "100Mb"

class CPUs(object):
    @staticmethod
    def CPUs4():
        return 4
    @staticmethod
    def CPUs2():
        return 2
    @staticmethod
    def CPUs1():
        return 1

class RAM(object):
    @staticmethod
    def to_sl(ram):
        if not type(ram) is str:
            raise TypeError("String expected")
        elif ram == RAM.GB1():
            return 1
        elif ram == RAM.GB2():
            return 2
        elif ram == RAM.GB4():
            return 4
        elif ram == RAM.GB8():
            return 8
        else:
            raise ValueError("One of {}, {}, {} or {} expected".format(RAM.GB1(), RAM.GB2(), RAM.GB4(), RAM.GB8()))
    
    @staticmethod
    def from_sl_mb(ram):
        return "{}GB".format(ram / 1024)
        
    @staticmethod
    def GB1():
        return "1GB"
    @staticmethod
    def GB2():
        return "2GB"
    @staticmethod
    def GB4():
        return "4GB"
    @staticmethod
    def GB8():
        return "8GB"
    
class VSInstanceConfig(VSInstanceConfigBasic):
    def __init__(self, ansible_config=None, sl_get_instance=None):
        if (ansible_config==None) == (sl_get_instance==None):
             self.__init_absent()
        elif ansible_config is not None:
            self.from_ansible_config(ansible_config)
        else:
            self.__from_sl(sl_get_instance)
        self.sl_data = sl_get_instance
       
    def __init_absent(self):
        self.from_ansible_config({"state":VSState.ABSENT()})
           
    def from_ansible_config(self, ansible_config):
        VSInstanceConfigBasic.from_ansible_config(self, ansible_config)
        self.state = ansible_config.get("state")
        self.payment_scheme = ansible_config.get("payment_scheme")
        self.dedicated = ansible_config.get("dedicated")
        self.datacenter = ansible_config.get("datacenter")
        self.os_code = ansible_config.get("os_code")
        self.private = ansible_config.get("private")
        self.post_install_script = ansible_config.get("post_install_script")
        if self.post_install_script == "":
            self.post_install_script = None
        if ansible_config.get("user_data") == "" \
            or ansible_config.get("user_data") is None:
            self.user_data = None
        else:
            self.user_data = ansible_config.get("user_data").replace("'", "\"")
        self.root_ssh_keys = ansible_config.get("root_ssh_keys")
        if self.root_ssh_keys is None:
            self.root_ssh_keys = []
        self.nic_speed = ansible_config.get("nic_speed")
        self.CPUs = int(ansible_config.get("CPUs"))
        self.RAM = ansible_config.get("RAM")
        
    def __from_sl(self, sl_data):
        self.state = self.__read_state_from_sl(sl_data)
        self.fqdn = "{}.{}".format(sl_data["hostname"], sl_data["domain"])
        if True == sl_data.get("hourlyBillingFlag", None):
            self.payment_scheme = VSPaymentScheme.HOURLY()
        else: self.payment_scheme = VSPaymentScheme.MONTHLY()
        self.dedicated = sl_data.get("dedicatedAccountHostOnlyFlag", False)
        self.datacenter = sl_data["datacenter"]["name"]
        self.os_code = sl_data["operatingSystem"]["softwareLicense"]["softwareDescription"]["referenceCode"]
        self.private = sl_data.get("privateNetworkOnlyFlag", False)
        self.post_install_script = sl_data.get("post_uri", None)
        self.root_ssh_keys = []
        self.nic_speed = self.__read_nic_speed_from_sl(sl_data)
        self.CPUs = sl_data["maxCpu"]
        self.RAM = RAM.from_sl_mb(sl_data["maxMemory"])
    
    def __read_state_from_sl(self, sl_data):
        sl_power_state = sl_data["powerState"]["keyName"]
        if sl_power_state == "RUNNING":
            return VSState.RUNNING()
        if sl_power_state == "HALTED":
            return VSState.PRESENT()
        # HALTED is also used during some of the transactions, when the host
        # is powered down.
        assert sl_power_state == "RUNNING" or sl_power_state == "HALTED"
    
    def __read_nic_speed_from_sl(self, sl_data):
        network_components = sl_data.get("networkComponents")
        if network_components is None or len(network_components) == 0:
            return 0
        eth1_speed = sl_data["networkComponents"][0]["maxSpeed"]
        eth2_speed = sl_data["networkComponents"][1]["maxSpeed"]
        if eth1_speed > eth2_speed:
            common_port_speed = eth1_speed
        else: common_port_speed = eth2_speed
        return NICSpeed.from_sl(common_port_speed)
        
    @staticmethod
    def arg_spec():
        new_args = dict(
            state = dict(type = 'str', default = VSState.RUNNING(), choices = [VSState.PRESENT(),VSState.RUNNING(), VSState.ABSENT()]),
            payment_scheme = dict(type = 'str', default = VSPaymentScheme.HOURLY(), choices = [VSPaymentScheme.HOURLY(), VSPaymentScheme.MONTHLY()]),
            dedicated = dict(type = 'bool', default=False),
            datacenter = dict(type ='str', required=True),
            os_code = dict(type='str', required=True),
            private = dict(type='bool', default=True),
            post_install_script = dict(type='str'),
            user_data = dict(type='str'),
            root_ssh_keys = dict(type='list'),
            nic_speed = dict(type='str', default = NICSpeed.Mb100(), choices = [NICSpeed.Mb100(), NICSpeed.Mb10(), NICSpeed.Gb1()]),
# due to bug https://github.com/ansible/ansible/issues/5463 ints cannot be really passed via variables
# so made it accept strings
            CPUs = dict(type='str', default = CPUs.CPUs1(), choices = [str(CPUs.CPUs1()), str(CPUs.CPUs2()), str(CPUs.CPUs4())]),
            RAM = dict(type='str', default = RAM.GB1(), choices = [RAM.GB1(), RAM.GB2(), RAM.GB4(), RAM.GB8()]),
            wait = dict(type='int', default=600)
        ) 
        return dict(new_args, **VSInstanceConfigBasic.arg_spec())   
    

class SoftlayerVirtualServer(SoftlayerVirtualServerBasic):
    _nothing = "nothing"
    _create = "created"
    _start = "started"
    _stop = "stopped"
    _cancel= "canceled"
    _recreated = "recreated"
    _upgraded = "upgraded"
    _os_reloaded = "os_reloaded"
    
    def __init__(self, sl_client, instance_config, wait):
        SoftlayerVirtualServerBasic.__init__(self, sl_client, instance_config)
        self._sl_ssh_keys_manager = SoftLayer.SshKeyManager(sl_client)
        self._wait = wait
    
    def sync_config(self, change_log):
        sync_instance_config = self.__get_vs_instance_config_in_sl()
        actionPerformed = self.__handleState(sync_instance_config, change_log)
        if actionPerformed == self._create or actionPerformed == self._cancel:
            return self.__result(True, actionPeformed)
        if actionPerformed == self._nothing and self.ic.state == VSState.ABSENT():
            return self.__result(True, actionPeformed)
        changed = actionPerformed != self._nothing   
        changed |= self.__handleSettingsRequiringInstanceRecreation(sync_instance_config, change_log)
        if changed:
            return self.__result(True, self._recreated)
        changed |= self.__handleUpgradableSettings(sync_instance_config, change_log)
        if changed:
            return self.__result(True, self._upgraded)
        changed |= self.__handleSettingsRequiringOsReload(sync_instance_config, change_log)
        if changed:
            return self.__result(True, self._os_reloaded)
        return self.__result(False, self._nothing)
    
    def __result(self, changed, action_performed):
        return {"changed": changed, "action_performed": action_performed}
    
    def __handleState(self, sync_instance_config, change_log):
        if sync_instance_config.state == self.ic.state:
            return self._nothing
        change_log.log("state", sync_instance_config.state, self.ic.state)
        if self.ic.state == VSState.RUNNING() and \
            sync_instance_config.state == VSState.ABSENT():
            self.create()
            return self._create
        if self.ic.state == VSState.RUNNING() and \
            sync_instance_config.state == VSState.PRESENT():
            self.power_on()
            return self._start
        if self.ic.state == VSState.PRESENT() and \
            sync_instance_config.state == VSState.ABSENT():
            self.create()
            self.power_off()
            return self._create
        if self.ic.state == VSState.PRESENT() and \
            sync_instance_config.state == VSState.RUNNING():
            self.power_off()
            return self._stop
        if self.ic.state == VSState.ABSENT():
            self.cancel()
            return self._cancel
    
    def create(self):
        try: 
            ssh_key_ids = self.__key_ids()
        except SSHKeyException as ssh_key_exception:
            raise VSException(False, ssh_key_exception.msg())
        
        create_params = self.__generate_create_dict(
            cpus = self.ic.CPUs,
            memory = RAM.to_sl(self.ic.RAM),
            hourly = VSPaymentScheme.to_sl(self.ic.payment_scheme),
            hostname = self.ic.get_host(),
            domain = self.ic.get_domain(),
            local_disk = False,
            datacenter = self.ic.datacenter,
            os_code = self.ic.os_code,
            dedicated = self.ic.dedicated,
            private = self.ic.private,
            post_uri = self.ic.post_install_script,
            ssh_keys = ssh_key_ids,
            nic_speed = NICSpeed.to_sl(self.ic.nic_speed),
            user_data = self.ic.user_data
        )
        print "create_params: ", create_params
        with open('/home/hristo/data.txt', 'w') as outfile:
            json.dump(create_params, outfile)
        self.sl_virtual_guest.createObject(create_params)
        self.__wait_for_ready()
        
    def __generate_create_dict(
            self, cpus=None, memory=None, hourly=True,
            hostname=None, domain=None, local_disk=True,
            datacenter=None, os_code=None, image_id=None,
            dedicated=False, public_vlan=None, private_vlan=None,
            nic_speed=None, user_data=None, disks=None, post_uri=None,
            private=False, ssh_keys=None):
        """Returns a dict appropriate to pass into Virtual_Guest::createObject
            See :func:`create_instance` for a list of available options.
        """
        required = [cpus, memory, hostname, domain]

        mutually_exclusive = [
            {'os_code': os_code, "image_id": image_id},
        ]

        if not all(required):
            raise ValueError("cpu, memory, hostname, and domain are required")

        for mu_ex in mutually_exclusive:
            if all(mu_ex.values()):
                raise ValueError(
                    'Can only specify one of: %s' % (','.join(mu_ex.keys())))

        data = {
            "startCpus": int(cpus),
            "maxMemory": int(memory),
            "hostname": hostname,
            "domain": domain,
            "localDiskFlag": local_disk,
        }

        data["hourlyBillingFlag"] = hourly

        if dedicated:
            data["dedicatedAccountHostOnlyFlag"] = dedicated

        if private:
            data['privateNetworkOnlyFlag'] = private

        if image_id:
            data["blockDeviceTemplateGroup"] = {"globalIdentifier": image_id}
        elif os_code:
            data["operatingSystemReferenceCode"] = os_code

        if datacenter:
            data["datacenter"] = {"name": datacenter}

        if public_vlan:
            data.update({
                'primaryNetworkComponent': {
                    "networkVlan": {"id": int(public_vlan)}}})
        if private_vlan:
            data.update({
                "primaryBackendNetworkComponent": {
                    "networkVlan": {"id": int(private_vlan)}}})

        if user_data:
            data['userData'] = [
                                {
                                 'value': user_data,
                                 'type': {
                                          'keyname': 'USER_DATA',
                                          'name': 'User Data'
                                        }
                                 }
                               ]

        if nic_speed:
            data['networkComponents'] = [{'maxSpeed': nic_speed}]

        if disks:
            data['blockDevices'] = [
                {"device": "0", "diskImage": {"capacity": disks[0]}}
            ]

            for dev_id, disk in enumerate(disks[1:], start=2):
                data['blockDevices'].append(
                    {
                        "device": str(dev_id),
                        "diskImage": {"capacity": disk}
                    }
                )

        if post_uri:
            print "post_uri", post_uri
            data['postInstallScriptUri'] = post_uri

        if ssh_keys:
            data['sshKeys'] = [{'id': key_id} for key_id in ssh_keys]

        return data
    
    def __wait_for_ready(self):
        if self._wait == 0:
            return 
        if not self.sl_vs_manager.wait_for_ready(self.get_vs_id(), self._wait, 5, True):
            raise VSException(true, "Instance {}.{} did not complete transaction in the specified timeout {}"
                          .format(self.ic.get_host(), self.ic.get_domain(), self._wait)) 
        
    def power_off(self):
        self.sl_virtual_guest.powerOffSoft(id=self.get_vs_id())
        self.__wait_for_ready()
    
    def power_on(self):
        self.sl_virtual_guest.powerOn(id=self.get_vs_id())
        self.__wait_for_ready()
    
    def cancel(self):
        self.sl_vs_manager.cancel_instance(self.get_vs_id())
        self.__wait_for_cancel()
    
    def __wait_for_cancel(self):
        time_to_wait_until = time.time() + self._wait
        while time.time() <= time_to_wait_until:
            if self.get_vs_id(False) is not None:
                time.sleep(2)
            else: return
        raise VSException("Unable to cancel instance {} in the specified timeout {}".format(self.ic.fqdn, self.ic.wait))        
        
    def __handleSettingsRequiringInstanceRecreation(self, sync_instance_config, change_log):
        changed = False
        if sync_instance_config.dedicated != self.ic.dedicated:
            change_log.log("dedicated", sync_instance_config.dedicated, self.ic.dedicated)
            changed = True
        if sync_instance_config.datacenter != self.ic.datacenter:
            change_log.log("datacenter",  sync_instance_config.datacenter, self.ic.datacenter)
            changed = True
        if sync_instance_config.os_code != self.ic.os_code:
            change_log.log("os_code", sync_instance_config.os_code, self.ic.os_code)
            changed = True
        if sync_instance_config.payment_scheme != self.ic.payment_scheme:
            change_log.log("payment_scheme", sync_instance_config.payment_scheme, self.ic.payment_scheme)
            changed = True
        if sync_instance_config.private != self.ic.private:
            change_log.log("private", sync_instance_config.private, self.ic.private)
            changed = True
        if changed:
            self.cancel()
            self.create()
        return changed
    
    def __handleUpgradableSettings(self, sync_instance_config, change_log):
        changed = sync_instance_config.CPUs != self.ic.CPUs
        if sync_instance_config.CPUs != self.ic.CPUs:
            change_log.log("CPUs", sync_instance_config.CPUs, self.ic.CPUs)
        if sync_instance_config.RAM != self.ic.RAM:
            change_log.log("RAM", sync_instance_config.RAM, self.ic.RAM)
            changed = true;
        
#        if changed:
#             self.sl_vs_manager.upgrade(instance_id=self.get_vs_id(),
#                                         cpus=self.ic.CPUs,
#                                         memory=RAM.to_sl(self.ic.RAM))
        
        nic_speed_changed = sync_instance_config.nic_speed != self.ic.nic_speed
        if nic_speed_changed:
            change_log.log("nic_speed", sync_instance_config.nic_speed, self.ic.nic_speed)
#            self.sl_vs_manager.change_port_speed(instance_id=self.get_vs_id(),
#                                                  public=False,
#                                                  speed=NICSpeed.to_sl(self.ic.nic_speed))
#            if self.ic.private:
#                self.sl_vs_manager.change_port_speed(instance_id=self.get_vs_id(),
#                                                      public=True,
#                                                      speed=NICSpeed.to_sl(self.ic.nic_speed))
        changed = changed or nic_speed_changed
        self.__wait_for_ready()
        return changed
    
    def __handleSettingsRequiringOsReload(self, sync_instance_config, change_log):
        changed = False
        if sync_instance_config.post_install_script != self.ic.post_install_script:
             change_log.log("post_install_script", sync_instance_config.post_install_script,  self.ic.post_install_script)
             changed = True
        if not (set(sync_instance_config.root_ssh_keys).issubset(set(self.ic.root_ssh_keys)) and \
            set(sync_instance_config.root_ssh_keys).issuperset(set(self.ic.root_ssh_keys))):
            change_log.log("root_ssh_keys", sync_instance_config.root_ssh_keys, self.ic.root_ssh_keys)
            changed = True
       
        if changed :
            self.sl_vs_manager.reload_instance(instance_id=self.get_vs_id(),
                                                post_uri=self.ic.post_install_script,
                                                ssh_keys=self.ic.root_ssh_keys)
            self.__wait_for_ready()
        return changed  
    

    def __key_ids(self):
        key_ids = []
        for key_label in self.ic.root_ssh_keys:
            found_label = self.single_result(self._sl_ssh_keys_manager.list_keys(label=key_label))
            if found_label is None:
                raise SSHKeyException("SSH Key with label {} not found".format(key_label))
            key_ids.append(found_label["id"])
        return key_ids
            
    
    def __get_vs_instance_config_in_sl(self):
        if self.get_vs_id() is None:
            return VSInstanceConfig(None, None)
#       make sure there's no transaction running before getting the instance
#       because it's very likely to change right after the transaction is finished
        self.__wait_for_ready()
        sl_data = self.sl_vs_manager.get_instance(self.get_vs_id())
        instance_config_in_sl = VSInstanceConfig(sl_get_instance=sl_data)
        instance_config_in_sl.root_ssh_keys = self.__get_ssh_keys_in_sl(self.get_vs_id())
#       loaded but currently unused. Difference between metadata in VM and
#       configuration will be ignored. This is because seting it via set_user_data metod
#       sets the new metadata in Softlayer model but doesn't update it on the filesystem
#       from where it is actually used by the scripts. Also to avoid very complicated
#       scripts for updating the filesystem it would be best to restart the system.
#       this would unfortunatelly lead to differences if later one changes the configuration
#       in git so that new vms are created with different metadata, for example different users
        instance_config_in_sl.user_data = self.__get_user_data(self.get_vs_id())
        return instance_config_in_sl  
    
    def __get_ssh_keys_in_sl(self, instance_id):
        label_ssh_key_map = self.sl_virtual_guest.getSshKeys(id=instance_id, mask="label")
        return map(lambda label_ssh_key_pair: label_ssh_key_pair["label"] , label_ssh_key_map)
    
    def __get_user_data(self, instance_id):
        user_data = self.sl_virtual_guest.getUserData(id=instance_id);
        if user_data is None:
            return None
        
        for user_data_entry in user_data:
            user_data_entry_type = user_data_entry["type"]
            if user_data_entry_type is not None and\
                user_data_entry_type["keyname"] == "USER_DATA" and\
                user_data_entry_type["name"] == "User Data":
                return user_data_entry["value"]
        return None

class ChangeLog(object):
    __dict = {}
    
    def log(self, field, old, new):
        self.__dict[field] = {"old": old, "new": new}
    
    def to_dict(self):
        return self.__dict
    
       
class VSException(Exception):
    def __init__(self, changed, msg):
        self._changed = changed
        self._msg = msg
    def __str__(self):
        return "Exception: {} Changed: {}, MSG: {}".format(type(self), self.changed(), self.msg())
    def changed(self):
        return self._changed
    def msg(self):
        return self._msg

class SSHKeyException(Exception):
    def __init__(self, msg):
        self._msg = msg
    def __str__(self):
        return "Exception: {}, MSG: {}".format(type(self), _msg)
    def msg(self):
        return self._msg
        
    
def main():
    
    module_helper = AnsibleModule(
        argument_spec = dict(
            SLClientConfig.arg_spec().items() + VSInstanceConfig.arg_spec().items()
        )
    )
    
    sl_client_config = SLClientConfig(module_helper.params)
    sl_client = SoftLayer.Client(username=sl_client_config.sl_username, api_key=sl_client_config.api_key)
    vs = SoftlayerVirtualServer(sl_client,
                                 VSInstanceConfig(ansible_config=module_helper.params),
                                  module_helper.params.get("wait"))
    try:
        change_log = ChangeLog()
        result = vs.sync_config(change_log)
        result['change_log'] = change_log.to_dict()
        module_helper.exit_json(**result)
    except VSException as se:
        module_helper.fail_json(changed=se.changed(), msg=str(se))

main()









