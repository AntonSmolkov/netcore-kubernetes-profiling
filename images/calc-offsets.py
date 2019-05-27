#!/usr/bin/env python

#
# calc-offsets.py <pid> <native image name>
#    e.g. calc-offsets.py 1234 sample-netcore-app.ni.exe
#
# Parses /tmp/<pid>/maps and /tmp/<native image name map> file and dumps a list
#  of offsets for all methods in the native image map file generated by crossgen.
#  These offsets are then usable in tools like perf and bcc for dynamic tracing
#

import argparse
import os
import re
import subprocess

class Section(object):
    def __init__(self, start, end, perms, offset, path):
        self.start = int(start, 16)
        self.end = int(end, 16)
        self.perms = perms
        self.offset = int(offset, 16)
        self.path = path

def all_sections(pid):
    sections = {}
    with open("/proc/%d/maps" % pid, "r") as maps:
        for line in maps:
            match = re.match(r"(\S+)-(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)", line.strip())
            if match is None:
                continue
            start, end, perms, offset, path = match.group(1, 2, 3, 4, 5)
            if '/' not in path:
                continue
            filename = os.path.basename(path)
            section = Section(start, end, perms, offset, path)
            if filename in sections:
                sections[filename].append(section)
            else:
                sections[filename] = [section]
    return sections

parser = argparse.ArgumentParser(description="Place dynamic tracing probes on a managed method " +
    "that resides in a crossgen-compiled assembly. For .NET Core on Linux.",
    epilog="EXAMPLE: ./place-probe.py 1234 sample-netcore-app.ni.exe")
parser.add_argument("pid", type=int, help="the dotnet process id")
parser.add_argument("nativeimage", type=str, help="name of the native image generated by crossgen")
args = parser.parse_args()

sections = all_sections(args.pid)

output = subprocess.check_output("cat /tmp/%s*map" % os.path.splitext(args.nativeimage)[0], shell=True)
assembly = args.nativeimage

for line in output.strip().split('\n'):
    parts = line.split()

    address = int(parts[0], 16)
    symbol = str.join(' ', parts[2:])

    first_section = sections[assembly][0]
    # exec section has to be be executable and contain the method in question
    exec_section = [section for section in sections[assembly]
                        if 'r-xp' == section.perms and
                           (section.start - first_section.start) < address and
                           (section.end - first_section.start) > address][0]

    offset_from_first = exec_section.start - first_section.start
    offset_in_file = exec_section.offset

    final_address = address - offset_from_first + offset_in_file

    print("offset: %x : %s" %
            (final_address, ' '.join(parts[2:]) ))