#!/usr/bin/env python
# import xml.etree.ElementTree as ET
import lxml.etree as ET


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
        if len(l_by_tag[l.tag]) == 1 and len(r_by_tag[l.tag]) == 1:
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


ltext="""
<a>
    <b t='1'></b>
    <c p='1'></c>
    <d><b x='4'>a</b></d>
    <d>foo</d>
    <d>baz</d>
    <e />
    <e a="1"/>
    <e />
</a>"""
rtext="""
<a>
    <b t='2'></b>
    <c p='1'></c>
    <d><b x='4'>a</b></d>
    <d>foo</d>
    <d>bar</d>
    <e a="1"/>
    <e />
</a>"""

lxml = ET.fromstring(ltext)
rxml = ET.fromstring(rtext)

print xml_cmp(lxml,rxml)

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

#print ET.tostring(lxml,pretty_print=True)
#print ET.tostring(rxml,pretty_print=True)
indent(lxml)
indent(rxml)
print ET.tostring(lxml)
print ET.tostring(rxml)
