#!/usr/bin/env python

try:
    import libvirt
except ImportError:
    installed_libvirt_py = False
else:
    installed_libvirt_py = True

import re  # to handle whitespace
import xml.dom.minidom

from pprint import pprint  # FIXME

from ansible.module_utils.basic import AnsibleModule
# from ansible.module_utils._text import to_native


def strip_whitespace(s):
    return re.sub(r"\s+", "", s, flags=re.UNICODE)


def find_in(element, collection, function=lambda x, y: x == y):
    return next((item for item in collection if function(element, item)), None)


def findElement(root, name):
    f = lambda x, y: hasattr(y, "tagName") and y.tagName == x
    return find_in(name, root, f)


def xml_match(left, right):
    ''' checks if all DOM elements on left tree are found in the right tree
    and have the same attributes and values. Left and right tree could still
    differ since the right one may contain elements which are not present on
    the left.'''
    # compare tag names
    if not (hasattr(left, "tagName") and hasattr(right, "tagName") and
            left.tagName == right.tagName):
        return False

    # compare attributes
    for a in left.attributes.items():
        if a[1] != right.getAttribute(a[0]):
            return False

    # compare child nodes for equality
    for l in left.childNodes:
        if hasattr(l, "tagName"):  # recurse on subtree
            if not find_in(l, right.childNodes, xml_match):
                # a matching subtree could not be found on right side
                return False
        elif hasattr(l, "data"):  # check plain element equality
            if len(strip_whitespace(l.data)) != 0:  # skip whitespaces
                if not find_in(l, right.childNodes,
                               lambda x, y: x.data == y.data):
                    # unable to find element on right side with identical data
                    return False
        else:
            raise Exception("xml parsing error: unknown element")
    else:
        return True  # all nodes found a matching node on the right side


# e=findElement(xml_dom.documentElement, "devices")
# print xml_match(e, e)
# print xml_match(xml_file.documentElement, xml_dom.documentElement)
#
# created: running but not defined! (intermediate) FIXME
# absent: equals undefined
# present: in any state not being undefined
# latest: in any state not being undefined keeping syntax up to date
# saved: state is defined (not running) and there is a savefile present TODO
# rebooted? (Maybe, shutdown and start work also. :-/)

all_states_neg = ['absent', 'undefined']
all_states_soft = ['present', 'latest']
all_states_pos_real = ['defined', 'running', 'paused']
all_states_pos = all_states_soft + all_states_pos_real
all_states = all_states_neg + all_states_pos


def hard_state(state, default):
    ''' gets desired state of the domain given a 'soft' state definition.
        A soft state may be something like 'latest' which means to keep the
        current state unless it is undefined. therefore the parameter default
        should be set to the current domain state'''
    if state in all_states_pos_real:
        return state
    elif state in all_states_neg:
        return 'undefined'
    else:
        return default if default in all_states_pos_real else 'defined'


def dom_state(domain):
    ''' receives state of domain by domain handle. If a falsey domain handle
        is given (e.g. None) state 'unknown' is emitted.
        returns: Tuple of (state, strange), where state is the domains state
            and strange is True if libvirt returns a state like 'blocked' or
            'pmsuspended'. However, those states should never appear. '''

    # notice that there is no "undefined" state returned here since that
    # causes the domain to be nonexistent.
    states = {
        libvirt.VIR_DOMAIN_NOSTATE: ('running', True),
        libvirt.VIR_DOMAIN_BLOCKED: ('running', True),
        libvirt.VIR_DOMAIN_RUNNING: ('running', False),
        libvirt.VIR_DOMAIN_PAUSED: ('paused', False),
        libvirt.VIR_DOMAIN_SHUTDOWN: ('defined', False),
        libvirt.VIR_DOMAIN_SHUTOFF: ('defined', False),
        libvirt.VIR_DOMAIN_CRASHED: ('unknown', True),
        libvirt.VIR_DOMAIN_PMSUSPENDED: ('unknown', True),
    }

    if not domain:
        return 'undefined', False

    dom_state, _ = domain.state()  # get domain state from libvirt
    return states.get(dom_state, ('unknown', True))


def main():
    # domains in negative state can not be found

    module = AnsibleModule(argument_spec=dict(
        name=dict(aliases=['guest']),
        state=dict(choices=all_states, default='present'),
        force_state=dict(type='bool', default=False),  # use 'destroy' if true
        uri=dict(default='qemu:///system'),
        force_xml=dict(type='bool', default=False),  # 'latest' regarless state
        xml=dict(),
        sections=dict(),
    ))
    result = dict(changed=False, message='')

    if not installed_libvirt_py:
        module.fail_json(msg="'libvirt' python library is missing on host.")

    # connect to libvirt host
    conn = libvirt.open(module.params['uri'])
    if not conn:
        module.fail_json(msg="connection to libvirt failed.")

    # find domain
    domain_handle = None
    try:
        domain_handle = conn.lookupByName(module.params['name'])
    except libvirt.libvirtError as e:
        if(e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN):
            module.fail_json(msg=str(e), debug=e.get_error_code())

    # evaluate domain state ... first get current state
    current_state, strange_state = dom_state(domain_handle)
    if current_state == 'undefined' \
            and module.params['state'] not in all_states_neg \
            and not ('xml' in module.params and module.params['xml']):
        module.fail_json(msg="domain not found and no definition given.")

    # find out what state the user wants the domain to be in
    desired_state = hard_state(module.params['state'], default=current_state)

    if current_state != desired_state:
        # transition!
        result['changed'] = True
    elif module.params['state'] == 'latest':
        # fetch domains XML definition and compare to module paramters
#        dom_xml = xml.dom.minidom.parseString(domain_handle.XMLDesc(0))
#        if 'xml' in module.params and module.params['xml']:
#            def_xml = xml.dom.minidom.parseString(module.params['xml'])
#            if xml_match(def_xml.documentElement, dom_xml.documentElement):
#                result['changed'] = True
#        if 'sections' in module.params and module.params['sections']:
        result['changed'] = True
        pass  # FIXME
    else:
        result['changed'] = False

    if not module.check_mode and result['changed']:
        # ensure xml to be written contains sections defined!
        # merge with existing XML to keep things like mac addresses
        pass  # really do something FIXME

    module.exit_json(**result)

#    if not domain_handle:
#        if not 'xml' in module.params or not module.params['xml']:
#            module.fail_json(msg="domain not found and no definition given.")

if __name__ == '__main__':
    main()

# xml_dom = xml.dom.minidom.parseString(vm_handle.XMLDesc(0))
# xml_file = xml.dom.minidom.parseString(xml_raw_file)

# pprint(xml_dom.documentElement.childNodes)
# pprint(dir(xml_dom.documentElement))
# print(vm_handle.XMLDesc(0))
