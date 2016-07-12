#   Copyright 2014 Derrick J. Wippler
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from six import string_types
from configparser import NoSectionError, NoOptionError
from configparser import RawConfigParser, _UNSET
from itertools import chain
import os


class ListConfigParser(RawConfigParser):
    def __init__(self, *args, **kwargs):
        super(ListConfigParser, self).__init__(*args, **kwargs)

        self._converters.update(
            list=self.list_converter
        )

    @staticmethod
    def list_converter(value):
        if isinstance(value, string_types):
            value = filter(None, (i.strip() for i in value.splitlines()))
        return list(value)


class InheritanceConfigParser(ListConfigParser):
    def _supersections(self, section):
        try:
            section_names = self.list_converter(self._sections[section]['%inherit'])
        except KeyError:
            return []

        sections = [self._sections[section] for section in section_names]

        # nested inheritance
        hypersections = (self._supersections(section_name) for section_name in section_names)

        return chain(sections, *hypersections)


    def _unify_values(self, section, vars):
        '''Inject supersections into the correct position in the inheritance
        chain.

        '''
        chain = super(InheritanceConfigParser, self)._unify_values(section, vars)

        chain.maps[2:2] = self._supersections(section)

        return chain

    def items(self, section=_UNSET, raw=False, vars=None):
        '''This is actually an upstream bug, imo.

        '''

        d = self._unify_values(section, vars)

        value_getter = lambda option: self._interpolation.before_get(self,
            section, option, d[option], d)
        if raw:
            value_getter = lambda option: d[option]

        return [(self.optionxform(option), value_getter(option)) for option in d.keys()]


class SafeConfigParser(InheritanceConfigParser):
    """ Simple subclass to add the safeGet() method """
    def getError(self):
        return None

    def safeGet(self, section, key):
        try:
            return super(SafeConfigParser, self).get(section, key)
        except (NoSectionError, NoOptionError):
            return None


class ErrorConfigParser(SafeConfigParser):
    """ Simple subclass to inform users of a parse error """
    def __init__(self, msg):
        SafeConfigParser.__init__(self)
        self.msg = msg

    def getError(self):
        return self.msg


def openFd(file):
    """ Open the file if possible, else return None """
    try:
        return open(file)
    except IOError:
        return None

def readConfigs(files=None, default_section=None):
    """ Given a list of file names, return a list of handles to succesfully opened files"""
    files = files or [os.path.expanduser('~/.hubblerc'), '.hubblerc']
    # If non of these files exist, raise an error
    if not any([os.path.exists(rc) for rc in files]):
        return ErrorConfigParser("Unable to find config files in these"
                                 " locations [%s]" % ", ".join(files))
    return parseConfigs([openFd(file) for file in files], default_section)


def parseConfigs(fds, default_section=None):
    """ Given a list of file handles, parse all the files with ConfigParser() """
    # Read the config file
    config = SafeConfigParser(default_section=default_section)
    # Don't transform (lowercase) the key values
    config.optionxform = str
    # Read all the file handles passed
    for fd in fds:
        if fd is None:
            continue
        config.readfp(fd)
        config.name = fd.name
    return config


def validateVariableExists(args):
    """ Throw is the env and the variable does not exist in the config """
    conf = readConfigs()
    if conf.getError():
        raise RuntimeError(conf.getError())

    try:
        # attempt to get the variable from the requested environment
        conf.get(args.env, args.variable)
    except NoSectionError as e:
        raise RuntimeError("No such environment [%s] in '%s'" %
                           (args.env, conf.name))
    except NoOptionError:
        raise RuntimeError("No such variable '%s' for environment [%s] exists"
                           " in '%s'" % (args.variable, args.env, conf.name))
