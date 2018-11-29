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

def define_net(conn,name,xmldef,autostart):
    # TODO: Ensure name matches XML
    net=conn.networkDefineXML(xmldef);
    net.setAutostart(autostart)
    net.create()


def undefine_net(net_handle):
    if net_handle.isActive():
        net_handle.destroy()
    net_handle.undefine()

all_states=['present','absent','leases']

def main():
    module = AnsibleModule(argument_spec=dict(
        name=dict(aliases=['net'],required=True),
        state=dict(choices=all_states, default='present'),
        uri=dict(default='qemu:///system'),
        autostart=dict(default=True), # FIXME: change is not implemented yet
        xml=dict(),
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

    net_handle = None

    # look for network
    try:
        net_handle = conn.networkLookupByName(module.params['name'])
    except libvirt.libvirtError as e:
        if e.get_error_code() != libvirt.VIR_ERR_NO_NETWORK:
            module.fail_json(msg=str(e), debug=(e.get_error_code(), str(e)))

    # apply state
    if not net_handle and module.params['state']=='present':
        result['changed']=True

        if not 'xml' in module.params or not module.params['xml']:
            module.fail_json(msg="you should define a xml")

        if not module.check_mode:
            define_net(conn,module.params['name'],module.params['xml'])
    elif net_handle and module.params['state']=='absent':
        result['changed']=True
        if not module.check_mode:
            undefine_net(net_handle)
    elif module.params['state']=='leases':
        if not net_handle:
            module.fail_json(msg="net does not exist")
        result['changed']=False
        result['leases']=net_handle.DHCPLeases()

    module.exit_json(**result)
        
if __name__ == '__main__':
    main()
