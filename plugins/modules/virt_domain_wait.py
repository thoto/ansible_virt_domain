#!/usr/bin/env python

try:
    import libvirt
except ImportError:
    installed_libvirt_py = False
else:
    installed_libvirt_py = True

import datetime
import time

from ansible.module_utils.basic import AnsibleModule

def eh_dummy(x, y):
    """ dummy error handler to supress error messages to stderr """
    pass


def dom_state(domain):
    ''' receives state of domain by domain handle. If a falsey domain handle
        is given (e.g. None) state 'unknown' is emitted.
        returns: Tuple of (state, strange), where state is the domains state
            and strange is True if libvirt returns a state like 'blocked' or
            'pmsuspended'. However, those states should never appear. '''

    # notice that there is no "undefined" state returned here since that
    # causes the domain to be nonexistent.
    states = {
        libvirt.VIR_DOMAIN_NOSTATE:     ('running', True),
        libvirt.VIR_DOMAIN_BLOCKED:     ('running', True),
        libvirt.VIR_DOMAIN_RUNNING:     ('running', False),
        libvirt.VIR_DOMAIN_PAUSED:      ('running', False), # FIXME
        libvirt.VIR_DOMAIN_SHUTDOWN:    ('present', False),
        libvirt.VIR_DOMAIN_SHUTOFF:     ('present', False),
        libvirt.VIR_DOMAIN_CRASHED:     ('unknown', True),
        libvirt.VIR_DOMAIN_PMSUSPENDED: ('unknown', True),
    }

    if not domain:
        return 'absent', False

    dom_state, _ = domain.state()  # get domain state from libvirt
    return states.get(dom_state, ('unknown', True))


all_states=['present','running','absent']

def main():
    module = AnsibleModule(argument_spec=dict(
        name=dict(aliases=['guest'],required=True),
        state=dict(choices=all_states, default='running'),
        uri=dict(default='qemu:///system'),
        sleep=dict(type='int', default=10),
        timeout=dict(type='int', default=60*60),
    ), supports_check_mode=True)
    result = dict(changed=False, message='')

    if not installed_libvirt_py:
        module.fail_json(msg="'libvirt' python library is missing on host.")
    libvirt.registerErrorHandler(eh_dummy, 'ctx')  # apply dummy error handler

    # connect to libvirt host
    conn = libvirt.openReadOnly(module.params['uri'])
    if not conn:
        module.fail_json(msg="connection to libvirt failed.")

    # find domain
    domain_handle = None
    try:
        domain_handle = conn.lookupByName(module.params['name'])
    except libvirt.libvirtError as e:
        if(e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN):
            module.fail_json(msg=str(e), debug=e.get_error_code())

    end = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=module.params['timeout'])

    while datetime.datetime.utcnow() < end:
        # evaluate domain state ... first get current state
        current_state, strange_state = dom_state(domain_handle) # FIXME
        if current_state == module.params['state']:
            result['message']="state reached"
            break
        elif current_state == 'unknown':
            module.fail_json(msg="invalid state")
            break
        time.sleep(module.params['sleep'])

    module.exit_json(**result)
        
if __name__ == '__main__':
    main()
