# `virt_domain` module
test repo: alternate `virt_domain` module for ansible which should replace
the `virt` module.

The code can be found at `/library/virt_domain.py`. There is an example
playbook at `/test.yml` using a domain template `/templates/dom.xml.j2`.
There are many bugs and issues listed in file BUGS. Documentation should
be written too and put inside the module as by ansibles module
specification. The current version does not do anything yet and is considered
work-in-progress.
