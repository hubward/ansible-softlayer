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
    hostname:
        description:
            - Hostname of the instance. This is not the fully qualified domain name
            - but only the instance name
        type: string
        required: true
    domain:
        description
            - The domain of the instance
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
    
class VSInstanceConfig(object):
    def __init__(self, ansible_config=None, sl_get_instance=None):
        if (ansible_config==None) == (sl_get_instance==None):
             self._init_absent()
        elif ansible_config is not None:
            self._from_ansible_config(ansible_config)
        else:
            self._from_sl(sl_get_instance)
        self.sl_data = sl_get_instance
       
    def _init_absent(self):
        self._from_ansible_config({"state":VSState.ABSENT()})
           
    def _from_ansible_config(self, ansible_config):
        self.state = ansible_config.get("state")
        self.hostname = ansible_config.get("hostname")
        self.domain = ansible_config.get("domain");
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
        self.CPUs = ansible_config.get("CPUs")
        self.RAM = ansible_config.get("RAM")
        
    def _from_sl(self, sl_data):
        self.state = self._read_state_from_sl(sl_data)
        self.hostname = sl_data["hostname"]
        self.domain = sl_data["domain"]
        if True == sl_data.get("hourlyBillingFlag", None):
            self.payment_scheme = VSPaymentScheme.HOURLY()
        else: self.payment_scheme = VSPaymentScheme.MONTHLY()
        self.dedicated = sl_data.get("dedicatedAccountHostOnlyFlag", False)
        self.datacenter = sl_data["datacenter"]["name"]
        self.os_code = sl_data["operatingSystem"]["softwareLicense"]["softwareDescription"]["referenceCode"]
        self.private = sl_data.get("privateNetworkOnlyFlag", False)
        self.post_install_script = sl_data.get("post_uri", None)
        self.root_ssh_keys = []
        self.nic_speed = self._read_nic_speed_from_sl(sl_data)
        self.CPUs = sl_data["maxCpu"]
        self.RAM = RAM.from_sl_mb(sl_data["maxMemory"])
    
    def _read_state_from_sl(self, sl_data):
        sl_power_state = sl_data["powerState"]["keyName"]
        if sl_power_state == "RUNNING":
            return VSState.RUNNING()
        if sl_power_state == "HALTED":
            return VSState.PRESENT()
        # HALTED is also used during some of the transactions, when the host
        # is powered down.
        assert sl_power_state == "RUNNING" or sl_power_state == "HALTED"
    
    def _read_nic_speed_from_sl(self, sl_data):
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
        return dict(
            state = dict(type = 'str', default = VSState.RUNNING(), choices = [VSState.PRESENT(),VSState.RUNNING(), VSState.ABSENT()]),
            hostname = dict(type = 'str', required=True),
            domain=dict(type= 'str', required=True),
            payment_scheme = dict(type = 'str', default = VSPaymentScheme.HOURLY(), choices = [VSPaymentScheme.HOURLY(), VSPaymentScheme.MONTHLY()]),
            dedicated = dict(type = 'bool', default=False),
            datacenter = dict(type ='str', required=True),
            os_code = dict(type='str', required=True),
            private = dict(type='bool', default=True),
            post_install_script = dict(type='str'),
            user_data = dict(type='str'),
            root_ssh_keys = dict(type='list'),
            nic_speed = dict(type='str', default = NICSpeed.Mb100(), choices = [NICSpeed.Mb100(), NICSpeed.Mb10(), NICSpeed.Gb1()]),
            CPUs = dict(type='int', default = CPUs.CPUs1(), choices = [CPUs.CPUs1(), CPUs.CPUs2(), CPUs.CPUs4()]),
            RAM = dict(type='str', default = RAM.GB1(), choices = [RAM.GB1(), RAM.GB2(), RAM.GB4(), RAM.GB8()]),
            wait = dict(type='int', default=600)
        )    
    

class SoftlayerVirtualServer(object):
    _cached_sl_instance_id = None
    _nothing = 0
    _create = 1
    _start = 2
    _stop = 3
    _cancel= 4
    
    def __init__(self, sl_client, instance_config, wait):
        self._sl_vs_manager = SoftLayer.VSManager(sl_client)
        self._sl_ssh_keys_manager = SoftLayer.SshKeyManager(sl_client)
        self._sl_virtual_guest = sl_client['Virtual_Guest']
        self._ic = instance_config
        self._wait = wait
    
    def sync_config(self):
        sync_instance_config = self._get_vs_instance_config_in_sl()
        actionPerformed = self._handleState(sync_instance_config)
        if actionPerformed == self._create or actionPerformed == self._cancel:
            return True
        if actionPerformed == self._nothing and self._ic.state == VSState.ABSENT():
            return False
        changed = actionPerformed != self._nothing
        changed |= self._handleSettingsRequiringInstanceRecreation(sync_instance_config)
        if changed:
            return True 
        changed |= self._handleUpgradableSettings(sync_instance_config)
        changed |= self._handleSettingsRequiringOsReload(sync_instance_config)
        return changed
    
    def _handleState(self, sync_instance_config):
        if sync_instance_config.state == self._ic.state:
            return self._nothing
        if self._ic.state == VSState.RUNNING() and \
            sync_instance_config.state == VSState.ABSENT():
            self.create()
            return self._create
        if self._ic.state == VSState.RUNNING() and \
            sync_instance_config.state == VSState.PRESENT():
            self.power_on()
            return self._start
        if self._ic.state == VSState.PRESENT() and \
            sync_instance_config.state == VSState.ABSENT():
            self.create()
            self.power_off()
            return self._create
        if self._ic.state == VSState.PRESENT() and \
            sync_instance_config.state == VSState.RUNNING():
            self.power_off()
            return self._stop
        if self._ic.state == VSState.ABSENT():
            self.cancel()
            return self._cancel
    
    def create(self):
        try: 
            ssh_key_ids = self._key_ids()
        except SSHKeyException as ssh_key_exception:
            raise VSException(False, ssh_key_exception.msg())
        
        create_params = self._generate_create_dict(
            cpus = self._ic.CPUs,
            memory = RAM.to_sl(self._ic.RAM),
            hourly = VSPaymentScheme.to_sl(self._ic.payment_scheme),
            hostname = self._ic.hostname,
            domain = self._ic.domain,
            local_disk = False,
            datacenter = self._ic.datacenter,
            os_code = self._ic.os_code,
            dedicated = self._ic.dedicated,
            private = self._ic.private,
            post_uri = self._ic.post_install_script,
            ssh_keys = ssh_key_ids,
            nic_speed = NICSpeed.to_sl(self._ic.nic_speed),
            user_data = self._ic.user_data
        )
        print "create_params: ", create_params
        with open('/home/hristo/data.txt', 'w') as outfile:
            json.dump(create_params, outfile)
        self._sl_virtual_guest.createObject(create_params)
        self._wait_for_ready()
        
    def _generate_create_dict(
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
            data['postInstallScriptUri'] = post_uri

        if ssh_keys:
            data['sshKeys'] = [{'id': key_id} for key_id in ssh_keys]

        return data
    
    def _wait_for_ready(self):
        if self._wait == 0:
            return 
        if not self._sl_vs_manager.wait_for_ready(self.get_vs_id(), self._wait, 5, True):
            raise VSException(true, "Instance {}.{} did not complete transaction in the specified timeout {}"
                          .format(self._ic.hostname, self._ic.domain, self._wait)) 
        
    def power_off(self):
        self._sl_virtual_guest.powerOffSoft(id=self.get_vs_id())
        self._wait_for_ready()
    
    def power_on(self):
        self._sl_virtual_guest.powerOn(id=self.get_vs_id())
        self._wait_for_ready()
    
    def cancel(self):
        self._sl_vs_manager.cancel_instance(self.get_vs_id())
        self._wait_for_cancel()
    
    def _wait_for_cancel(self):
        time_to_wait_until = time.time() + self._wait
        while time.time() <= time_to_wait_until:
            if self.get_vs_id(False) is not None:
                time.sleep(2)
            else: return
        raise VSException("Unable to cancel instance {} in the specified timeout {}".format(self.fq_name(), self._ic.wait))        
        
    def _handleSettingsRequiringInstanceRecreation(self, sync_instance_config):
        changed = sync_instance_config.dedicated != self._ic.dedicated or \
            sync_instance_config.datacenter != self._ic.datacenter or \
            sync_instance_config.os_code != self._ic.os_code or \
            sync_instance_config.payment_scheme != self._ic.payment_scheme or \
            sync_instance_config.private != self._ic.private
        # changing user data/metadata requires instance recreation because
        # just calling Virtual_Guest::setUserMetadata updates the data in
        # the Softlayer model but doesn't update it on the file syste i.e.
        # on /dev/xvdha1/meta.js.          
            
        if changed:
            self.cancel()
            self.create()
        return changed
    
    def _handleUpgradableSettings(self, sync_instance_config):
        changed = sync_instance_config.CPUs != self._ic.CPUs or \
            sync_instance_config.RAM != self._ic.RAM or\
            sync_instance_config.nic_speed != self._ic.nic_speed
        if changed:
            self._sl_vs_manager.upgrade(instance_id=self.get_vs_id(),
                                        cpus=self._ic.CPUs,
                                        memory=RAM.to_sl(self._ic.RAM))
        
        nic_speed_changed = sync_instance_config.nic_speed != self._ic.nic_speed
        if nic_speed_changed:
           self._sl_vs_manager.change_port_speed(instance_id=self.get_vs_id(),
                                                 public=False,
                                                 speed=NICSpeed.to_sl(self._ic.nic_speed))
           if self._ic.private:
               self._sl_vs_manager.change_port_speed(instance_id=self.get_vs_id(),
                                                     public=True,
                                                     speed=NICSpeed.to_sl(self._ic.nic_speed))
        changed = changed or nic_speed_changed
        self._wait_for_ready()
        return changed
    
    def _handleSettingsRequiringOsReload(self, sync_instance_config):
        changed = sync_instance_config.post_install_script != self._ic.post_install_script\
        or \
            not (set(sync_instance_config.root_ssh_keys).issubset(set(self._ic.root_ssh_keys)) and \
            set(sync_instance_config.root_ssh_keys).issuperset(set(self._ic.root_ssh_keys)))\
       
        if changed :
            self._sl_vs_manager.reload_instance(instance_id=self.get_vs_id(),
                                                post_uri=self._ic.post_install_script,
                                                ssh_keys=self._ic.root_ssh_keys)
            self._wait_for_ready()
        return changed  
    
    def fq_name(self):
        return "{}.{}".format(self._ic.hostname, self._ic.domain)

    def _key_ids(self):
        key_ids = []
        for key_label in self._ic.root_ssh_keys:
            found_label = self._single_result(self._sl_ssh_keys_manager.list_keys(label=key_label))
            if found_label is None:
                raise SSHKeyException("SSH Key with label {} not found".format(key_label))
            key_ids.append(found_label["id"])
        return key_ids
            
    
    def get_vs_id(self, cached_id=True):
        if cached_id == True and self._cached_sl_instance_id is not None:
            return self._cached_sl_instance_id
        result = self._single_result(
            self._sl_vs_manager.list_instances(
                hostname=self._ic.hostname,
                domain=self._ic.domain,
                mask="id"))
        if result is None:
            _cached_sl_instance_id = None
            return None
        elif not cached_id:
            self._cached_sl_instance_id = None
        else:
            self._cached_sl_instance_id = result.get("id")
        return result.get("id")
        
    def _get_vs_instance_config_in_sl(self):
        if self.get_vs_id() is None:
            return VSInstanceConfig(None, None)
#       make sure there's no transaction running before getting the instance
#       because it's very likely to change right after the transaction is finished
        self._wait_for_ready()
        sl_data = self._sl_vs_manager.get_instance(self.get_vs_id())
        instance_config_in_sl = VSInstanceConfig(sl_get_instance=sl_data)
        instance_config_in_sl.root_ssh_keys = self._get_ssh_keys_in_sl(self.get_vs_id())
#       loaded but currently unused. Difference between metadata in VM and
#       configuration will be ignored. This is because seting it via set_user_data metod
#       sets the new metadata in Softlayer model but doesn't update it on the filesystem
#       from where it is actually used by the scripts. Also to avoid very complicated
#       scripts for updating the filesystem it would be best to restart the system.
#       this would unfortunatelly lead to differences if later one changes the configuration
#       in git so that new vms are created with different metadata, for example different users
        instance_config_in_sl.user_data = self._get_user_data(self.get_vs_id())
        return instance_config_in_sl  
    
    def _get_ssh_keys_in_sl(self, instance_id):
        label_ssh_key_map = self._sl_virtual_guest.getSshKeys(id=instance_id, mask="label")
        return map(lambda label_ssh_key_pair: label_ssh_key_pair["label"] , label_ssh_key_map)
    
    def _get_user_data(self, instance_id):
        user_data = self._sl_virtual_guest.getUserData(id=instance_id);
        if user_data is None:
            return None
        
        for user_data_entry in user_data:
            user_data_entry_type = user_data_entry["type"]
            if user_data_entry_type is not None and\
                user_data_entry_type["keyname"] == "USER_DATA" and\
                user_data_entry_type["name"] == "User Data":
                return user_data_entry["value"]
        return None
    
    def _single_result(self, result_list):
        if len(result_list) == 0:
            return None
        else: return result_list[0]  
        
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
    sl_client = SoftLayer.Client(sl_client_config.sl_username, sl_client_config.api_key)
    vs = SoftlayerVirtualServer(sl_client,
                                 VSInstanceConfig(ansible_config=module_helper.params),
                                  module_helper.params.get("wait"))
    try:
        module_helper.exit_json(changed = vs.sync_config())
    except VSException as se:
        module_helper.fail_json(changed=se.changed(), msg=str(se))

main()









