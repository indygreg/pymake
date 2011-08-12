#!/usr/bin/env python

'''CLI for trace parser

Authored by Gregory Szorc <gregory.szorc@gmail.com>. All rights reserved.
'''

from optparse import OptionParser
from pymake.traceparser import TraceParser
import sys

def main(argv):
    op = OptionParser()
    op.add_option('--print-target-counts',
                  dest='print_target_counts',
                  default=False,
                  action='store_true',
                  help='Print each target and a count of how often it was evaluated')
    op.add_option('--print-command-list',
                  dest='print_command_list',
                  default=False,
                  action='store_true',
                  help='Print a raw list of commands that were executed')
    op.add_option('--print-command-counts',
                  dest='print_command_counts',
                  default=False,
                  action='store_true',
                  help='Print counts of how often individual commands were executed')

    options, args = op.parse_args()

    if not len(args):
        print 'Must supply exactly at least one path to a file to analyze'
        sys.exit(1)

    for path in args:
        parser = TraceParser(path)

        if options.print_target_counts:
            targets = parser.get_target_execution_counts()
            for k, v in targets.iteritems():
                print '%d\t%s' % ( v, k )

        if options.print_command_list:
            commands = parser.get_commands()
            for c in commands:
                print c[2]

        if options.print_command_counts:
            data = parser.get_executed_commands_report()
            for k, v in data['counts'].iteritems():
                print '%d\t%s' % ( v, k )

if __name__ == '__main__':
    main(sys.argv[1:])