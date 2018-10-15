#!/usr/bin/env python

try:
    import libvirt
except ImportError:
    installed_libvirt_py = False
else:
    installed_libvirt_py = True

import re  # to handle whitespace
import xml.etree.ElementTree as ET
import functools

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
        i.tail = ""  # remove tail since we aggregate in l.text!
    e.text = t
    return t

ign=""

def xml_cmp(left, right, alter=True, ignores={}):
    ''' if alter is given: report change by returning false AND alter right
    tree. otherwise just return false if a alteration of the right tree would
    be needed. '''
    global ign
    assert left.tag == right.tag
    ret = True

    my_ignores = ignores[left.tag] if left.tag in ignores else {}

    # parse attribute equality
    attr_add = {}
    for lk, lv in left.attrib.iteritems():
        if lk not in right.attrib or right.attrib[lk] != lv:
            if alter:
                right.set(lk, lv)
            if alter:  # FIXME integrate below
                ret = False
            if lk not in my_ignores: # ignore certain matches
                ret = False
            else:
                ign+="IGNORED l:"+lk+"="+lv+";"

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
        if my_ignores is not True:
            ret = False
        else:
            ign+="IGNORED: "+l_text+" on "+left.tag
        if alter:
            right.text = l_text


    for l in left:
        if (len(l_by_tag[l.tag]) == 1 and l.tag in r_by_tag and
                len(r_by_tag[l.tag]) == 1):
            # 1:1 tag match so alter this element instead of adding a new one
            ret = xml_cmp(l, r_by_tag[l.tag][0], alter, my_ignores) and ret
        else:
            # got multiple elements: compare but don't alter each one first.
            # After this add elements to the right side which could not be
            # matched. this also adds left elements missing on right side.
            # TODO: match each element just once! (remove best match?)
            for r in r_by_tag[l.tag] if l.tag in r_by_tag else []:
                if xml_cmp(l, r, False, my_ignores): # found match
                    # apply changes on previously ignored attributes first
                    ret = xml_cmp(l, r, True, my_ignores) and ret
                    break
            else: # none found: append whole subtree
                ret = False
                if alter:  # notice: iterating over r_by_tag not right!
                    right.append(l)
    return ret


def xml_sections(left, right, sections):
    return False


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


class virt_domain(object):
    def __init__(self, domain_handle, conn, xml, wait):
        self.domain_handle = domain_handle
        self.conn = conn
        self.xml = xml
        self.wait = wait

    def create(self):
        # FIXME: implement wait (state=running)
        self.domain_handle = self.conn.createXML(self.xml)  # TODO: Test
        return self.domain_handle

    def define(self):  # TODO: Test (+ state)
        self.domain_handle = self.conn.defineXML(self.xml)
        return self.domain_handle

    def undefine(self):
        return not self.domain_handle.undefine()  # TODO: Test (+ state)

    def start(self):
        # FIXME: implement wait (state=running)
        res = not self.domain_handle.create()
        return res  # TODO: Test

    def _wait(self, target):
        # TODO: check if state from array applies?
        while True:  # FIXME: count and evaluate duration (self.wait)
            try:
                r = self.domain_handle.state()[0]
            except libvirt.libvirtError as e:
                if(e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN):
                    return True
            if r == target:
                return True

    def shutdown(self):
        r = self.domain_handle.shutdown()
        if self.wait:
            self._wait(libvirt.VIR_DOMAIN_SHUTOFF)
        return not r

    def destroy(self):
        r = self.domain_handle.destroy()
        if self.wait:
            self._wait(libvirt.VIR_DOMAIN_SHUTOFF)
        return not r

    def pause(self):
        # FIXME: implement wait (state=?)
        return self.domain_handle.suspend()  # TODO: Test

    def resume(self):
        # FIXME: implement wait (state=?)
        return self.domain_handle.resume()  # TODO: Test


def state_transition(current_state, target_state, transient=False,
                     graceful=True):
    assert(current_state != target_state)

    # define the table of state transitions and functions to use
    # function 'f' transitions from state 's' to state 'd'
    if transient:  # transient means a domain has no 'defined' state
        trans = [{'s': "undefined", 'd': "running", 'f': virt_domain.create},
                 {'s': "defined", 'd': "undefined", 'f': virt_domain.undefine}]
        off_target = "undefined"  # target state for shutdown
    else:
        trans = [{'s': "undefined", 'd': "defined", 'f': virt_domain.define},
                 {'s': "defined", 'd': "running", 'f': virt_domain.start},
                 {'s': "defined", 'd': "undefined", 'f': virt_domain.undefine}]
        off_target = "defined"

    if graceful:  # don't kill the vm using destroy but use shutdown
        trans += [{'s': "running", 'd': off_target, 'f': virt_domain.shutdown}]
    else:
        trans += [{'s': "running", 'd': off_target, 'f': virt_domain.destroy}]

    # other states (paused and saved for later use)
    trans += [{'s': "running", 'd': "paused", 'f': virt_domain.pause},
              {'s': "paused", 'd': "running", 'f': virt_domain.resume}]
#              {'s': "running", 'd': "saved", 'f': f_save},
#              {'s': "saved", 'd': "running", 'f': f_restore},]

    def find_state(st_from, st_to, t):
        """ find path from state 'st_from' to state 'st_to' using transition
        table 't'. returns list of dicts from 't' along path """
        # function does converge, but I'm not sure its result is always correct

        # first try to find direct transition
        t_match = [x for x in t if st_from == x['s'] and st_to == x['d']]
        if t_match:
            return [t_match[0]]
        else:  # there is no direct transition so find path between states
            # t_0: all transitions which originate from state st_from
            t_0 = [x for x in t if st_from == x['s']]

            # t_n: new transition table which does not contain transitions
            # originating from state st_from. generating this new transition
            # table for further processing makes the algorithm terminate
            # since we never reach the originating state again.
            t_n = [x for x in t if st_from != x['s'] and st_from != x['d']]

            # find transition paths from destination states in 't_n' which
            # lead to 'st_to'. this is a recusion so we always get paths.
            r = [[x] + find_state(x['d'], st_to, t_n)
                 for x in t_0 if find_state(x['d'], st_to, t_n)]

            return min(r, key=len) if r else []  # find minimal transition path

    def chain(a, b):
        """ retuns a function which executes b(...) after a(...). """
        return lambda *args, **kwargs: \
            a(*args, **kwargs) and b(*args, **kwargs)

    # return one (chained) function which transitions domain as defined
    return functools.reduce(lambda x, y: chain(x, y['f']) if x else y['f'],
                            find_state(current_state, target_state, trans),
                            False)


def eh_dummy(x, y):
    """ dummy error handler to supress error messages to stderr """
    pass


def main():
    # domains in negative state can not be found

    module = AnsibleModule(argument_spec=dict(
        name=dict(aliases=['guest']),
        state=dict(choices=all_states, default='present'),
        graceful=dict(type='bool', default=True),  # use 'destroy' if false
        wait=dict(type='int', default=0),
        uri=dict(default='qemu:///system'),
        latest=dict(type='bool', default=False),  # 'latest' regarless state
        xml=dict(),
        sections=dict(),
        transient=dict(type='bool', default=False),  # TODO rename persistent?
        debug_out_path=dict(),
    ), supports_check_mode=True)
    result = dict(changed=False, message='')

    if not installed_libvirt_py:
        module.fail_json(msg="'libvirt' python library is missing on host.")

    libvirt.registerErrorHandler(eh_dummy, 'ctx')  # apply dummy error handler

    # connect to libvirt host
    conn = libvirt.open(module.params['uri']) if not module.check_mode else \
        libvirt.openReadOnly(module.params['uri'])
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
    if module.params['transient'] and desired_state == "defined":
        module.fail_json(msg="transient domain can not be defined.")

    # xml defined at parameters
    xml_def = ET.fromstring(module.params['xml']) \
        if 'xml' in module.params and module.params['xml'] else None
    if xml_def: # FIXME Future warning here
        result['defined_xml'] = ET.tostring(xml_def)  # FIXME: remove!
    # current domain definition (via dumpxml)
    xml_curr = ET.fromstring(domain_handle.XMLDesc(0)) \
        if domain_handle else None
    if xml_curr:
        result['current_xml'] = ET.tostring(xml_curr)  # FIXME: remove!
    # xml to be applied by module
    xml_apply = None

    ignores = {
            "domain": {
                "devices": {
                    "disk": { "boot": { "order": True } },
                    "interface": { "boot": { "order": True } }
                    },
                "os": {"nvram": True }
                }
            }

    # parse xml and find difference if 'latest' is specified
    if current_state == 'undefined' and current_state != desired_state:
        # there is no previous XML given, so apply xml definition
        if 'sections' in module.params and module.params['sections']:
            xml_sections(xml_def, None, module.params['sections'])
        xml_apply = ET.tostring(xml_def)
    elif module.params['state'] == 'latest' or module.params['latest']:
        # calculate difference of currently running xml and desired xml
        if not (('xml' in module.params and module.params['xml']) or
                ('sections' in module.params and module.params['sections'])):
            module.fail_json(msg="neither XML nor sections were defined " +
                                 "but state should be latest.")

        if 'sections' in module.params and module.params['sections']:
            result['changed'] = \
                xml_sections(xml_def, xml_curr, module.params['sections']) \
                or result['changed']
        if 'xml' in module.params and module.params['xml']:
            xml_same = xml_cmp(xml_def, xml_curr, True, ignores)
            result['tree'] = ET.tostring(xml_curr)
            if not xml_same:
                result['changed'] = True
        xml_apply = ET.tostring(xml_curr)

    # calculate state transition
    method = None
    if current_state != desired_state:
        result['changed'] = True
        method = state_transition(current_state, desired_state,
                                  transient=module.params['transient'],
                                  graceful=module.params['graceful'])

    if not module.check_mode and result['changed']:
        if xml_apply and not current_state == "undefined":
            if 'debug_out_path' in module.params \
                    and module.params['debug_out_path']:
                with open(module.params['debug_out_path'],'w') as f:
                    f.write(xml_apply)
            conn.defineXML(xml_apply)
        if method:
            vd = virt_domain(domain_handle, conn, xml=xml_apply,
                             wait=module.params['wait'])
            st_result = method(vd)
            if not st_result:
                module.fail_json(msg="transitioning between states failed.",
                                 res=st_result)
    global ign
    result['ignored_parts']=ign
    module.exit_json(**result)


if __name__ == '__main__':
    main()
