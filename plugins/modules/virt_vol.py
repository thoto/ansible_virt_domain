#!/usr/bin/env python

# NOTICE: this module is very basic and missing a lot of features

try:
    import libvirt
except ImportError:
    installed_libvirt_py = False
else:
    installed_libvirt_py = True

import re

from ansible.module_utils.basic import AnsibleModule

def eh_dummy(x, y):
    """ dummy error handler to supress error messages to stderr """
    pass

all_states=['present','absent']

def get_capacity(capdef):
    m=re.compile("^[0-9]+[.]?[0-9]*").match(capdef)
    if m:
        unit=capdef[m.end():].strip()
        if unit=='':
            unit='bytes'
        if unit in ['B','bytes','KB','K','KiB', 'MB','M','MiB', 'GB','G','GiB',
            'TB','T','TiB', 'PB','P','PiB', 'EB','E','EiB']:
            return {'value':capdef[:m.end()],'unit':unit}
    

def define_vol(pool,name,capacity,thin=True):
    return pool.createXML("<volume type='block'> <name>%s</name> "%name +
        "<capacity unit='%s'>%s</capacity>"%(capacity['unit'],
            capacity['value']) +
        ("<allocation>0</allocation>" if thin else "") + "</volume>")

def undefine_vol(disk):
    disk.delete()

all_states=['present','absent']

def main():
    module = AnsibleModule(argument_spec=dict(
        pool=dict(required=True),
        name=dict(aliases=['vol'],required=True),
        state=dict(choices=all_states, default='present'),
        uri=dict(default='qemu:///system'),
        capacity=dict(aliases=['size']),
        allocation=dict(choices=['thin','fat'], default='thin'),
        ),
    supports_check_mode=True)
    result = dict(changed=False, message='')

    if not installed_libvirt_py:
        module.fail_json(msg="'libvirt' python library is missing on host.")
    libvirt.registerErrorHandler(eh_dummy, 'ctx')  # apply dummy error handler

    # connect to libvirt host
    conn = libvirt.open(module.params['uri']) if not module.check_mode else \
        libvirt.openReadOnly(module.params['uri'])
    if not conn:
        module.fail_json(msg="connection to libvirt failed.")

    pool_handle = None
    disk_handle = None

    # look for volume
    try:
        pool_handle = conn.storagePoolLookupByName(module.params['pool'])
        disk_handle = pool_handle.storageVolLookupByName(module.params['name'])
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_STORAGE_POOL:
            module.fail_json(msg="no such pool", debug=(e.get_error_code(),
                str(e)))
        elif e.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_VOL:
            module.fail_json(msg=str(e), debug=e.get_error_code())

    # apply state
    if not disk_handle and module.params['state']=='present':
        result['changed']=True

        # determine capacity first
        if not 'capacity' in module.params:
            module.fail_json(msg="you should define a capacity")
        capacity=get_capacity(module.params['capacity'])
        if not capacity:
            module.fail_json(msg="invalid capacity format")

        if not module.check_mode:
            disk_handle = define_vol(
                pool_handle, module.params['name'], capacity,
                thin=(module.params['allocation'] == 'thin'))
    elif disk_handle and module.params['state'] == 'absent':
        result['changed']=True
        if not module.check_mode:
            undefine_vol(disk_handle)
            disk_handle = None

    if disk_handle:
        result['disk_path'] =  disk_handle.path()
    module.exit_json(**result)


if __name__ == '__main__':
    main()
