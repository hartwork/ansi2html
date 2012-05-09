#  This file is part of ansi2html
#  Convert ANSI (terminal) colours and attributes to HTML
#  Copyright (C) 2012  Ralph Bean <rbean@redhat.com>
#
#  Inspired by and developed off of the work by pixelbeat and blackjack.
#
#  This program is free software: you can redistribute it and/or
#  modify it under the terms of the GNU General Public License as
#  published by the Free Software Foundation, either version 3 of
#  the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see
#  <http://www.gnu.org/licenses/>.
from __future__ import print_function

import re
import sys
import optparse

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from .style import template as style_template
import six
from six.moves import map
from six.moves import zip

_template = six.u("""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset={output_encoding}">
<style type="text/css">{style}</style>
</head>
<body class="body_foreground body_background" style="font-size: {font_size};" >
<pre>
{content}
</pre>
</body>

</html>
""")


def linkify(line):
    for match in re.findall(r'https?:\/\/\S+', line):
        line = line.replace(match, '<a href="%s">%s</a>' % (match, match))

    return line


class CursorMoveUp(object):
    pass


class Ansi2HTMLConverter(object):
    """ Convert Ansi color codes to CSS+HTML

    Example:
    >>> conv = Ansi2HTMLConverter()
    >>> ansi = " ".join(sys.stdin.readlines())
    >>> html = conv.convert(ansi)
    """

    def __init__(self,
                 dark_bg=True,
                 font_size='normal',
                 linkify=False,
                 escaped=True,
                 output_encoding='utf-8',
                ):
        self.dark_bg = dark_bg
        self.font_size = font_size
        self.linkify = linkify
        self.escaped = escaped
        self.output_encoding = output_encoding
        self._attrs = None

        self.ansi_codes_prog = re.compile('\033\\[' '([\\d;]*)' '([a-zA-z])')

    def apply_regex(self, ansi):
        parts = self._apply_regex(ansi)
        parts = self._collapse_cursor(parts)
        parts = list(parts)

        if self.linkify:
            parts = [linkify(part) for part in parts]

        return "".join(parts)

    def _apply_regex(self, ansi):
        if self.escaped:
            specials = OrderedDict([
                ('&', '&amp;'),
                ('<', '&lt;'),
                ('>', '&gt;'),
            ])
            for pattern, special in specials.items():
                ansi = ansi.replace(pattern, special)

        # n_open is a count of the number of open tags
        # last_end is the index of the last end of a code we've seen
        n_open, last_end = 0, 0
        for match in self.ansi_codes_prog.finditer(ansi):
            yield ansi[last_end:match.start()]
            last_end = match.end()

            params, command = match.groups()

            if command not in 'mMA':
                continue

            # Special cursor-moving code.  The only supported one.
            if command == 'A':
                yield CursorMoveUp
                continue

            try:
                params = list(map(int, params.split(';')))
            except ValueError:
                params = [0]

            # Special control codes.  Mutate into an explicit-color css class.
            if params[0] in [38, 48]:
                params = ["%i-%i" % (params[0], params[2])] + params[3:]

            if params == [0]:
                # If the control code 0 is present, close all tags we've
                # opened so far.  i.e. reset all attributes
                yield '</span>' * n_open
                n_open = 0
                continue

            # Count how many tags we're opening
            n_open += 1
            css_classes = " ".join(["ansi%s" % str(p) for p in params])
            yield '<span class="%s">' % css_classes

        yield ansi[last_end:]

    def _collapse_cursor(self, parts):
        """ Act on any CursorMoveUp commands by deleting preceding tokens """

        final_parts = []
        for part in parts:

            # Throw out empty string tokens ("")
            if not part:
                continue

            # Go back, deleting every token in the last 'line'
            if part == CursorMoveUp:
                final_parts.pop()
                while '\n' not in final_parts[-1]:
                    final_parts.pop()

                continue

            # Otherwise, just pass this token forward
            final_parts.append(part)

        return final_parts

    def prepare(self, ansi=''):
        """ Load the contents of 'ansi' into this object """

        body = self.apply_regex(ansi)

        self._attrs = {
            'dark_bg': self.dark_bg,
            'font_size': self.font_size,
            'body': body,
        }

        return self._attrs

    def attrs(self):
        """ Prepare attributes for the template """
        if not self._attrs:
            raise Exception("Method .prepare not yet called.")
        return self._attrs

    def convert(self, ansi, full=True):
        attrs = self.prepare(ansi)
        if not full:
            return attrs["body"]
        else:
            return _template.format(
                style=style_template(self.dark_bg),
                font_size=self.font_size,
                content=attrs["body"],
                output_encoding=self.output_encoding,
            )

    def produce_headers(self):
        return '<style type="text/css">{style}</style>\n'.format(
            style=style_template(self.dark_bg)
        )


def main():
    """
    $ ls --color=always | ansi2html > directories.html
    $ sudo tail /var/log/messages | ccze -A | ansi2html > logs.html
    $ task burndown | ansi2html > burndown.html
    """

    parser = optparse.OptionParser(usage=main.__doc__)
    parser.add_option(
        "-p", "--partial", dest="partial",
        default=False, action="store_true",
        help="Process lines as them come in.  No headers are produced.")
    parser.add_option(
        "-H", "--headers", dest="headers",
        default=False, action="store_true",
        help="Just produce the <style> tag.")
    parser.add_option(
        "-f", '--font-size', dest='font_size',
        default="normal",
        help="Set the global font size in the output.")
    parser.add_option(
        "-l", '--light-background', dest='light_background',
        default=False, action="store_true",
        help="Set output to 'light background' mode.")
    parser.add_option(
        "-i", '--linkify', dest='linkify',
        default=False, action="store_true",
        help="Transform URLs into <a> links.")
    parser.add_option(
        "-u", '--unescape', dest='escaped',
        default=True, action="store_false",
        help="Don't escape xml tags found in the input.")
    parser.add_option(
        '--output-encoding', dest='output_encoding',
        default='utf-8',
        help="Output encoding")

    opts, args = parser.parse_args()

    conv = Ansi2HTMLConverter(
        dark_bg=not opts.light_background,
        font_size=opts.font_size,
        linkify=opts.linkify,
        escaped=opts.escaped,
        output_encoding=opts.output_encoding,
    )

    # Produce only the headers and quit
    if opts.headers:
        print(conv.produce_headers())
        return

    # Process input line-by-line.  Produce no headers.
    if opts.partial:
        line = sys.stdin.readline()
        while line:
            # Strip newlines
            print(conv.convert(ansi=line, full=False)[:-1], end=' ')
            line = sys.stdin.readline()
        return

    # Otherwise, just process the whole thing in one go
    print(conv.convert(
        " ".join(sys.stdin.readlines())
    ).encode(opts.output_encoding))