# `virt_domain` module
test repo: alternate `virt_domain` module for ansible which should replace
the `virt` module.

The code can be found at `/library/virt_domain.py`. There is an example
playbook at `/test.yml` using a domain template `/templates/dom.xml.j2`.
There are many bugs and issues listed in file BUGS. Documentation should
be written too and put inside the module as by ansibles module
specification. The current version does not do anything yet and is considered
work-in-progress.

There is also a very basic and low quality `virt_vol` module to be found in
`/library/`. It just provides a very basic interface to create and destroy
volumes inside a pool. It does not match if the specification applies to the
volume and never changes parameters on an existing volume. Since both modules
share some code segments it might be considered to create a
`module_utils` library.

