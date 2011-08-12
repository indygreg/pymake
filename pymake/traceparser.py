# Authored by Gregory Szorc <gregory.szorc@gmail.com>. All rights reserved.

import json
import os.path

class TraceParser(object):
    '''Provides routines for analyzing trace files generated by
    running make.py --trace-log'''

    def __init__(self, path):
        '''Create a parser that operates on the path specified'''

        self.path = path

        with open(self.path, 'r') as f:
            l = f.readline()
            data = json.loads(l)

            assert data[0] == 'MAKEFILE_BEGIN'

            self.root_dir = data[2]['dir']

    def parse_file(self, callback, context=None):
        '''Parse the file the class was constructed with and call the
        supplied function with each event read

        The callback will receive in the following order:
          - str action performed
          - float time action performed
          - dict data in action
          - context passed into method
        '''
        with open(self.path, 'r') as f:
            for line in f:
                try:
                    o = json.loads(line)
                    callback(o[0], o[1], o[2], context)

                except ValueError, e:
                    pass

    def get_target_execution_counts(self):
        '''Obtain a dictionary of target execution counts.

        Keys will be target names. Values will be integer times of execution.
        '''

        targets = {}

        def callback(action, time, data, context):
            if action != 'TARGET_BEGIN':
                return

            name = data['target']
            dir = data['dir']

            fullname = os.path.normpath(os.path.join(dir, name))

            if fullname.find(self.root_dir) == 0:
                fullname = fullname[len(self.root_dir):]

            if fullname in targets:
                targets[fullname] += 1
            else:
                targets[fullname] = 1

        self.parse_file(callback)
        return targets

    def get_jobs(self):
        '''Returns a list of jobs executed during trace.'''

        jobs = {}
        all = []

        def callback(action, time, data, context):
            if action == 'JOB_START':
                jobs[data['id']] = ( time, data )
                return

            if action == 'JOB_FINISH':
                id = data['id']

                # If this happens, the tracer is whacked.
                # TODO log a warning or something
                if id not in jobs:
                    return

                job = jobs[id]

                data = job[1]
                data['wall_time'] = time - job[0]
                all.append(data)

                l = []
                if data['executable']:
                    l.append(data['executable'])

                if data['shell']:
                    l.append(data['argv'])
                else:
                    l.extend(data['argv'])

                data['friendly_exec'] = ' '.join(l).replace('\n', '\\n')

                del jobs[id]

        self.parse_file(callback, jobs)
        return all

    def get_aggregate_jobs(self):
        '''Obtains job information then combines similar jobs.'''

        # Keys are normalized job type
        jobs = {}

        def create_record(name):
            return {
                'count': 0,
                'name': name,
                'wall_time': 0.0,
            }

        for job in self.get_jobs():
            record = None

            if job['shell']:
                if 'shell' in jobs:
                    record = jobs['shell']
                else:
                    record = create_record('shell')

            elif job['executable']:
                normalized = os.path.normpath(job['executable'])

                if normalized in jobs:
                    record = jobs[normalized]
                else:
                    record = create_record(normalized)
            else:
                command = job['argv'][0]

                if command in jobs:
                    record = jobs[command]
                else:
                    record = create_record(command)

            record['count'] += 1
            record['wall_time'] += job['wall_time']

            jobs[record['name']] = record

        return jobs.values()


    def get_executed_commands(self):
        '''Obtains a list of commands that were invoked during make process'''

        commands = []

        def callback(action, time, data, context):
            if action != 'COMMAND_CREATE':
                return

            if not len(data['cmd']):
                return

            commands.append((data['dir'], data['target'], data['cmd']))

        self.parse_file(callback)

        return commands

    def get_executed_commands_report(self):
        '''Obtains a report of the executed commands.

        The report classifies related commands, performs counts, etc. This is
        useful for seeing where hot spots in the build process are, etc.
        '''

        command_counts = {}

        for command in self.get_executed_commands():
            params = command[2].split()

            if not len(params):
                continue

            orig = params[0]
            base = os.path.basename(orig)

            # Many commands are wrapped by the main python executable. We
            # drill into them.
            # TODO this should probably be a positive filter instead of a
            # negative one
            if base.find('python') != -1 and base != 'pythonpath':
                if len(params) < 2:
                    if base in command_counts:
                        command_counts[base] += 1
                    else:
                        command_counts[base] = 1

                    continue

                real = params[1]

                if not os.path.isabs(real):
                    real = os.path.join(command[0], real)

                real = os.path.normpath(real)

                if real in command_counts:
                    command_counts[real] += 1
                else:
                    command_counts[real] = 1
            else:
                if orig in command_counts:
                    command_counts[orig] += 1
                else:
                    command_counts[orig] = 1

        return {
            'counts': command_counts
        }

    def print_execution_tree(self, f):
        context = {
            'current_dir': self.root_dir,
            'level': 0
        }

        def callback(action, time, data, context):
            if action == 'MAKEFILE_BEGIN':
                dir = data['dir']
                assert dir.find(self.root_dir) == 0

                context['current_dir'] = dir[len(self.root_dir):]
                print >> f, '%sNEW MAKEFILE: %s' % ( ' ' * context['level'], context['current_dir'] )
                context['level'] += 1

            elif action == 'MAKEFILE_FINISH':
                context['level'] -= 1
                print >> f, '%sEND MAKEFILE' % ( ' ' * context['level'] )

            elif action == 'TARGET_BEGIN':
                name = data['target']

                print >> f, '%sBEGIN TARGET: %s' % ( ' ' * context['level'], name )
                context['level'] += 1

            elif action == 'TARGET_FINISH':
                name = data['target']

                context['level'] -= 1
                print >> f, '%sEND TARGET %s' % ( ' ' * context['level'], name )

            elif action == 'COMMAND_CREATE':
                command = data['cmd']

                print >> f, '%s$ %s' % ( ' ' * context['level'], command )

            elif action == 'JOB_START':
                pass

            elif action == 'JOB_FINISH':
                pass

        self.parse_file(callback, context)
