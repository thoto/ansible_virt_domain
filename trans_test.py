#!/usr/bin/env python

from __future__ import print_function
from pprint import pprint
import functools


def state_transition(current_state, target_state, transient=False,
                     graceful=True):
    assert(current_state != target_state)

    # some dummy functions which apply a transition from one state to another
    def f_create(domain_handle, xml, wait=0):
        return print("create VM") or True

    def f_define(domain_handle, xml, wait=0):
        return print("define VM") or 123

    def f_undefine(domain_handle, xml=None, wait=0):
        return print("UNdefine VM") or True

    def f_start(domain_handle, xml=None, wait=0):
        return print("start VM") or True

    def f_shutdown(domain_handle, xml=None, wait=0):
        return print("shutdown VM") or True

    def f_destroy(domain_handle, xml=None, wait=0):
        return print("destroy VM") or True

    def f_pause(domain_handle, xml=None, wait=0):
        return print("pause VM") or 456

    def f_resume(domain_handle, xml=None, wait=0):
        return print("resume VM") or True

    # define the table of state transitions and functions to use
    # function 'f' transitions from state 's' to state 'd'
    if transient:  # transient means a domain has no 'defined' state
        trans = [{'s': "undefined", 'd': "running", 'f': f_create},
                 {'s': "defined", 'd': "undefined", 'f': f_undefine}]
        off_target = "undefined"  # target state for shutdown
    else:
        trans = [{'s': "undefined", 'd': "defined", 'f': f_define},
                 {'s': "defined", 'd': "running", 'f': f_start},
                 {'s': "defined", 'd': "undefined", 'f': f_undefine}]
        off_target = "defined"

    if graceful:  # don't kill the vm using destroy but use shutdown
        trans += [{'s': "running", 'd': off_target, 'f': f_shutdown}]
    else:
        trans += [{'s': "running", 'd': off_target, 'f': f_destroy}]

    # other states (paused and saved for later use)
    trans += [{'s': "running", 'd': "paused", 'f': f_pause},
              {'s': "paused", 'd': "running", 'f': f_resume}]
#              {'s': "running", 'd': "saved", 'f': f_save},
#              {'s': "saved", 'd': "running", 'f': f_restore},]

    def find_state(st_from, st_to, t):
        """ find path from state 'st_from' to state 'st_to' using transition
        table 't'. returns list of dicts from 't' along path """
        # function does converge, but I'm not sure its result is always correct

        # first try to find direct transition
        t_match = list(filter(lambda x:
                              st_from == x['s'] and st_to == x['d'], t))
        if t_match:
            return [t_match[0]]
        else:  # there is no direct transition so find path between states
            # t_0: all transitions which originate from state st_from
            t_0 = list(filter(lambda x: st_from == x['s'], t))

            # t_n: new transition table which does not contain transitions
            # originating from state st_from. generating this new transition
            # table for further processing makes the algorithm terminate
            # since we never reach the originating state again.
            t_n = list(filter(lambda x:
                              st_from != x['s'] and st_from != x['d'], t))

            # find transition paths from destination states in 't_n' which
            # lead to 'st_to'. this is a recusion so we always get paths.
            r = list(map(lambda x: [x] + find_state(x['d'], st_to, t_n), t_0))
            return min(r, key=len)  # find the minimal transition path

    def chain(a, b):
        """ retuns a function which executes b(...) after a(...). """
        return lambda domain_handle, xml, wait: \
            a(domain_handle, xml, wait) and b(domain_handle, xml, wait)

    # return one (chained) function which transitions domain as defined
    return functools.reduce(lambda x, y: chain(x, y['f']) if x else y['f'],
                            find_state(current_state, target_state, trans),
                            False)

# example
t_up = state_transition('undefined', 'paused', transient=False, graceful=True)
t_up(1, 2, 3)

t_ud = state_transition('undefined', 'defined', transient=False, graceful=True)
t_ud(1, 2, 3)
