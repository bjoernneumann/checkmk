#!/usr/bin/python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2014             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# tails. You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.
"""This is an unsorted collection of small unrelated helper functions which are
usable in all components of the Web GUI of Check_MK

Please try to find a better place for the things you want to put here."""

import sys
import re
import uuid
import marshal
import itertools
import six

if sys.version_info[0] >= 3:
    from pathlib import Path  # pylint: disable=import-error
else:
    from pathlib2 import Path  # pylint: disable=import-error

import cmk.utils.paths

from cmk.gui.i18n import _
from cmk.gui.log import logger
from cmk.gui.exceptions import MKUserError


def num_split(s):
    """Splits a word into sequences of numbers and non-numbers.

    Creates a tuple from these where the number are converted into int datatype.
    That way a naturual sort can be implemented.
    """
    parts = []
    for part in re.split(r'(\d+)', s):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(part)

    return tuple(parts)


def cmp_num_split(a, b):
    """Compare two strings, separate numbers and non-numbers from before."""
    return (num_split(a) > num_split(b)) - (num_split(a) < num_split(b))


def key_num_split(a):
    """Return a key from a string, separate numbers and non-numbers from before."""
    return num_split(a)


def is_allowed_url(url):
    """Checks whether or not the given URL is a URL it is allowed to redirect the user to"""
    # Also prevent using of "javascript:" URLs which could used to inject code
    parsed = six.moves.urllib.parse.urlparse(url)

    # Don't allow the user to set a URL scheme
    if parsed.scheme != "":
        return False

    # Don't allow the user to set a network location
    if parsed.netloc != "":
        return False

    # Don't allow bad characters in path
    if not re.match(r"[/a-z0-9_\.-]*$", parsed.path):
        return False

    return True


def validate_start_url(value, varprefix):
    if not is_allowed_url(value):
        raise MKUserError(
            varprefix,
            _("The given value is not allowed. You may only configure "
              "relative URLs like <tt>dashboard.py?name=my_dashboard</tt>."))


def cmp_version(a, b):
    """Compare two version numbers with each other
    Allow numeric version numbers, but also characters.
    """
    if a is None or b is None:
        return (a > b) - (a < b)
    aa = list(map(num_split, a.split(".")))
    bb = list(map(num_split, b.split(".")))
    return (aa > bb) - (aa < bb)


# TODO: Remove this helper function. Replace with explicit checks and covnersion
# in using code.
def savefloat(f):
    try:
        return float(f)
    except (TypeError, ValueError):
        return 0.0


# TODO: Remove this helper function. Replace with explicit checks and covnersion
# in using code.
def saveint(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


# We should use /dev/random here for cryptographic safety. But
# that involves the great problem that the system might hang
# because of loss of entropy. So we hope /dev/urandom is enough.
# Furthermore we filter out non-printable characters. The byte
# 0x00 for example does not make it through HTTP and the URL.
def get_random_string(size, from_ascii=48, to_ascii=90):
    """Generate a random string (no cryptographic safety)"""
    secret = ""
    urandom = open("/dev/urandom")
    while len(secret) < size:
        c = urandom.read(1)
        if ord(c) >= from_ascii and ord(c) <= to_ascii:
            secret += c
    return secret


def gen_id():
    """Generates a unique id"""
    try:
        return open('/proc/sys/kernel/random/uuid').read().strip()
    except IOError:
        # On platforms where the above file does not exist we try to
        # use the python uuid module which seems to be a good fallback
        # for those systems.
        return str(uuid.uuid4())


# This may not be moved to g, because this needs to be request independent
_failed_plugins = {}


# Load all files below share/check_mk/web/plugins/WHAT into a specified context
# (global variables). Also honors the local-hierarchy for OMD
# TODO: This is kept for pre 1.6.0i1 plugins
def load_web_plugins(forwhat, globalvars):
    _failed_plugins[forwhat] = []

    for plugins_path in [
            Path(cmk.utils.paths.web_dir, "plugins", forwhat),
            cmk.utils.paths.local_web_dir / "plugins" / forwhat,
    ]:
        if not plugins_path.exists():
            continue

        for file_path in sorted(plugins_path.iterdir()):
            try:
                if file_path.suffix == ".py" and not file_path.with_suffix(".pyc").exists():
                    exec (_drop_comments(file_path.open().read()), globalvars)

                elif file_path.suffix == ".pyc":
                    code_bytes = file_path.open().read()[8:]
                    code = marshal.loads(code_bytes)
                    exec(code, globalvars)  # yapf: disable

            except Exception as e:
                logger.exception("Failed to load plugin %s: %s", file_path, e)
                _failed_plugins[forwhat].append((str(file_path), e))


def _drop_comments(content):
    if six.PY3:
        return content

    # Files opened with Pathlib handler are by default unicode encoded,
    # which is what we want. We constantly use exec to load modules or user
    # defined scripts. In python2, it is not possible to exec a unicode
    # string, which in itself defines an encoding. Minimal example
    # exec(u'# coding=utf8')
    # Thus we just drop all comment lines

    return "\n".join(x for x in content.split('\n') if not x.lstrip().startswith("#"))


def get_failed_plugins():
    return list(itertools.chain(*_failed_plugins.values()))
