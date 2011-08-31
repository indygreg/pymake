#!/usr/bin/env python

'''CLI for trace parser

Authored by Gregory Szorc <gregory.szorc@gmail.com>. All rights reserved.
'''

from optparse import OptionParser
from pymake.traceparser import TraceParser, Trace
import os, sys

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
    op.add_option('--print-job-times',
                  dest='print_job_times',
                  default=False,
                  action='store_true',
                  help='Print wall clock execution times of all jobs')
    op.add_option('--print-aggregate-job-times',
                  dest='print_aggregate_job_times',
                  default=False,
                  action='store_true',
                  help='Like --print-job-times except it sums jobs of the same command')
    op.add_option('--print-make-times',
                  dest='print_make_times',
                  default=False,
                  action='store_true',
                  help='Prints execution times of all spawned PyMake instances.')
    op.add_option('--print-bsa',
                  dest='print_bsa',
                  default=False,
                  action='store_true',
                  help='Print a JSON string to be used by the BSA analyzer tool.')

    options, args = op.parse_args()

    if not len(args):
        print 'Must supply exactly at least one path to a file to analyze'
        sys.exit(1)

    for path in args:
        parser = None
        trace = None
        if options.print_bsa:
            trace = Trace(path)
        else:
            parser = TraceParser(path)

        if options.print_target_counts:
            targets = parser.get_target_execution_counts()
            for k, v in targets.iteritems():
                print '%d\t%s' % ( v, k )

        if options.print_command_list:
            commands = parser.get_executed_commands()
            for c in commands:
                print c['cmd']

        if options.print_job_times:
            for j in parser.get_jobs():
                print '%f\t%s' % ( j['wall_time'], j['friendly_exec'] )

        if options.print_aggregate_job_times:
            for j in parser.get_aggregate_jobs():
                print '%f\t%d\t%s' % ( j['wall_time'], j['count'], j['name'] )

        if options.print_make_times:
            for m in parser.get_pymake_instances():
                print '%f\t%s\t%s%s{%s}\t%s' % ( m['wall_time'], m['id'],
                    m['dir'], os.sep, ', '.join(m['files']),
                    ' '.join(m['targets']) )

        if options.print_bsa:
            trace.printbsa(sys.stdout)

if __name__ == '__main__':
    main(sys.argv[1:])
