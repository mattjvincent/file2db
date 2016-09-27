# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
from future.utils import bytes_to_native_str as n
from past.builtins import long


import argparse
import csv
import locale
import logging
import mmap
import os
import sys
import traceback
import types

from .compat import is_py2#, str, bytes, basestring




BAD_LEADING_CHARS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '_']
EMPTY_COLUMN_VALS = ['na', 'n/a', '(none)', '(null)', 'null']

def _show_error():
    """
    show system errors
    """
    et, ev, tb = sys.exc_info()

    print("Error Type: %s" % et)
    print("Error Value: %s" % ev)
    while tb :
        co = tb.tb_frame.f_code
        filename = str(co.co_filename)
        #line_no = str(traceback.tb_lineno(tb))
        line_no = 1
        print('    %s:%s' % (filename, line_no))
        traceback.print_tb(tb)
        tb = tb.tb_next

class File2DBParseError(Exception):
    pass


class Column(object):
    """ Simple class encapsulate meta data for a column

    """
    def __init__(self):
        self.name = None
        self.max_length = 0
        self.min_length = 0
        self.max_value = None
        self.min_value = None
        self.min_length_value = 0
        self.max_length_value = 0
        self.index = 0
        self.type = None
        self.empty = 0
        self.not_empty = 0

    def __str__(self):
        return 'Name: {} Type: {}'.format(self.name, self.type)


def parse_type(value):
    """
    Return converted value or raise File2DBParseError
    """
    #print('value=',value)
    #print (type(value))

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    if is_py2:
        if isinstance(value, unicode):
            return value.decode('ascii', 'ignore')

        if isinstance(value, str):
            return value

    else:
        if isinstance(value, bytes):
            return n(value)

        if isinstance(value, str):
            return value

    raise File2DBParseError('Unknown type')


def fix_column_name(column_name):
    """
    Remove bad characters

    :param column_name:
    :return:
    """
    column_name = column_name.replace('.', '_')
    column_name = column_name.replace(' ', '_')

    # eliminate columns starting with bad characters
    while column_name[0] in BAD_LEADING_CHARS:
        column_name = column_name[1:]

    return column_name


def _fixstr(s):
    #print('s=',s)
    #print (type(s))

    if is_py2:
        if isinstance(s, str):
            return str(s.decode('ascii', 'ignore'))
    else:
        if isinstance(s, bytes):
            return n(s)

        if isinstance(s, str):
            return s

    return str(s)


def qdf(c):
    """
    qdf = quick data fix
    Strip the trailing and leading spaces and/or replace with None
    """

    s = _fixstr(c)
    s = s.strip()

    if len(s) > 1 and (s[0] == '"' or s[0] == '\'') and (s[-1] == '"' or s[-1] == '\''):
        s = s[1:]
        s = s[:-1]

    t = s.lower()

    if len(t) == 0 or t in EMPTY_COLUMN_VALS:
        s = None

    return s


def qdf_row(row):
    """
    qdf = quick data fix
    Strip the trailing and leading spaces and/or replace with None
    """
    return map(qdf, row)


def count_lines(filename):
    f = open(filename, "r+")
    buf = mmap.mmap(f.fileno(), 0)
    lines = 0
    readline = buf.readline
    while readline():
        lines += 1
    return lines

def parse_file(input_file, delimiter, output_file=None, null_value=None, info_only=True):
    """
    Parse a file and gather statistics about each column.
    """
    col_info = []
    num_lines = count_lines(input_file)
    if num_lines == 0:
        logging.error("'{0}' contains no lines!!!".format(input_file))
        exit()

    line = 0

    try:
        reader = csv.reader(open(input_file), delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

        if not info_only:
            writer = csv.writer(open(output_file, "w"), delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        first_row = next(reader)
        i = 0
        line += 1

        logging.debug(first_row)

        # parse header or first row
        for h in first_row:
            c = Column()
            c.name = fix_column_name(h)
            c.index = i
            col_info.append(c)
            i += 1

        for row in reader:
            logging.debug(row)
            i = 0
            new_row = []
            for col in row:
                # handle nasty case where someone puts an extra delim at EOL
                if i >= len(col_info):
                    continue

                data = qdf(col)

                if data:
                    new_row.append(data)
                else:
                    new_row.append(null_value)

                c = col_info[i]

                # skip if no data
                if not data:
                    c.empty += 1
                else:
                    c.not_empty += 1
                    v = parse_type(data)
                    t = type(v)

                    #print('\ncurrent column: {}'.format(c))
                    #print('current value: {}, type: {}'.format(v, t))

                    dl = len(str(v))

                    if c.type is None:
                        c.type = t
                    elif c.type in (float, long, int):
                        # column is currently numeric
                        if t == str:
                            # new data is str
                            c.type = t
                            # TODO: this isn't the best way to handle this
                            c.max_value = str(c.max_value)
                            c.min_value = str(c.min_value)
                    elif c.type == str:
                        v = str(v)
                    else:
                        c.type = t

                    if c.max_value:
                        c.max_length = dl if dl > c.max_length else c.max_length
                        c.max_value = v if v > c.max_value else c.max_value
                    else:
                        c.max_value = v
                        c.max_length = dl

                    if c.min_value:
                        c.min_length = dl if dl < c.min_length else c.min_length
                        c.min_value = v if v < c.min_value else c.min_value
                    else:
                        c.min_value = v
                        c.min_length = dl

                col_info[i] = c

                i += 1
            line += 1

            if not info_only:
                writer.writerow(new_row)
    except Exception as inst:
        _show_error()
        print(str(inst))
        print("Line number: " + str(line))
        return None

    return col_info


