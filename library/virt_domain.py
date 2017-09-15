#!/usr/bin/env python

try:
    import libvirt
except ImportError:
    installed_libvirt_py = False
else:
    installed_libvirt_py = True

import re  # to handle whitespace
import xml.etree.ElementTree as ET

from ansible.module_utils.basic import AnsibleModule
# from ansible.module_utils._text import to_native  # FIXME: use it

def xml_by_tag_and_text(e):
    """ returns dict of (tag -> list of tags) in e. """
    r = {}
    for i in e:
        if i.tag not in r:
            r[i.tag] = []
        r[i.tag] += [i]
    return r

def xml_text(e):
    """ gets all direct text inside element """
    t = e.text.strip() if e.text else ""  # text summary
    for i in e:
        t += i.tail.strip() if i.tail else ""
        i.tail = "" # remove tail since we aggregate in l.text!
    e.text = t
    return t

# def xml_match_or_alter(left,right,alter=True):
def xml_cmp(left,right,alter=True):
    ''' if alter is given: report change by returning false AND alter right
    tree. otherwise just return false if a alteration of the right tree would
    be needed. '''
    assert left.tag == right.tag
    ret = True

    # parse attribute equality
    attr_add = {}
    for lk,lv in left.attrib.iteritems():
        if lk not in right.attrib or right.attrib[lk]!=lv:
            if alter:
                right.set(lk,lv)
            ret = False

    # sort elements by tag on each side
    l_by_tag = xml_by_tag_and_text(left)
    r_by_tag = xml_by_tag_and_text(right)

    # collect text content in l_text and r_text. this also manipulates
    # left.text and right.text to avoid dealing with text between elements
    # while altering text contents of elements. this also means text always
    # appears in front of tree.
    l_text = xml_text(left)
    r_text = xml_text(right)

    # compare text
    if l_text != r_text:
        ret = False
        if alter:
            right.text = l_text

    for l in left:
        if (len(l_by_tag[l.tag]) == 1 and l.tag in r_by_tag and
                len(r_by_tag[l.tag]) == 1):
            # 1:1 tag match so alter this element instead of adding a new one
            ret = xml_cmp(l,r_by_tag[l.tag][0],alter) and ret
        else:
            # got multiple elements: compare but don't alter each first
            # after that add elements to the right side which could not be
            # matched. this also adds left elements missing on right side.
            # TODO: match each element just once! (remove best match?)
            for r in r_by_tag[l.tag] if l.tag in r_by_tag else []:
                if xml_cmp(l,r,False):
                    break
            else:
                ret = False
                if alter:  # notice: iterating over r_by_tag not right!
                    right.append(l)
    return ret


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
        wait=dict(type='bool', default=False),
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

    curr_xml = None

    if current_state != desired_state:
        result['changed'] = True
    elif module.params['state'] == 'latest':
        # fetch domains XML definition and compare to module paramters
        curr_xml = ET.fromstring(domain_handle.XMLDesc(0))
        result['current_xml'] = ET.tostring(curr_xml)
        if 'xml' in module.params and module.params['xml']:
            def_xml = ET.fromstring(module.params['xml'])
            result['defined_xml'] = ET.tostring(def_xml)
            match = xml_cmp(def_xml,curr_xml,True)
            result['tree'] = ET.tostring(curr_xml)
            if not match:
                result['changed'] = True
        if 'sections' in module.params and module.params['sections']:
            pass  # FIXME
        if not (('xml' in module.params and module.params['xml']) or
                ('sections' in module.params and module.params['sections'])):
            result['message'] = "neither XML nor sections were checked " + \
                                "since none were given!"
    else:
        result['changed'] = False

    if not module.check_mode and result['changed']:
        # ensure xml to be written contains sections defined!
        # merge with existing XML to keep things like mac addresses
        pass  # really do something FIXME

    module.exit_json(**result)


if __name__ == '__main__':
    main()
