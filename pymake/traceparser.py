# Authored by Gregory Szorc <gregory.szorc@gmail.com>. All rights reserved.

import json
import os.path

class Trace(object):
    '''Represents a parsed PyMake trace'''
    def __init__(self, path):
        self.pymakes = {}
        self.root_pymake = None
        self.makefiles = {}
        self.targets = {}
        self.commands = {}
        self.initial_time = None
        self.timeline = []

        parser = TraceParser(path)

        parser.parse_file(self._parse_callback)

    def _parse_callback(self, action, time, data, context):
        if action == 'PYMAKE_BEGIN':
            id = data['id']

            entry = {
                'id':         id,
                'dir':        dir,
                'targets':    [],
                'time_start': time,
                'files':      data['makefiles']
            }

            if data['parent_id']:
                entry['parent_id'] = data['parent_id']
            else:
                self.root_pymake = id
                self.initial_time = time

            self.pymakes[id] = entry
            self.timeline.append((time, 'PYMAKE_BEGIN', id))

        elif action == 'PYMAKE_FINISH':
            id = data['id']
            if id not in self.pymakes:
                return

            entry = self.pymakes[id]
            entry['time_finish'] = time
            entry['time_wall'] = time - entry['time_start']

            self.timeline.append((time, 'PYMAKE_FINISH', id))

        elif action == 'MAKEFILE_CREATE':
            id = data['id']
            parent_id = data['context_id']

            entry = {
                'id':          id,
                'time_create': time,
                'targets':     [],
                'dir':         data['dir'],
                'parent_id':   parent_id,
            }

            self.makefiles[id] = entry

            if parent_id in self.pymakes:
                self.pymakes[parent_id]['targets'].append(id)

            self.timeline.append((time, 'MAKEFILE_CREATE', id))

        elif action == 'MAKEFILE_BEGIN':
            id = data['id']
            if id not in self.makefiles:
                return

            entry = self.makefiles[id]
            entry['time_begin'] = time
            entry['included']   = data['included']

            self.timeline.append((time, 'MAKEFILE_BEGIN', id))

        elif action == 'MAKEFILE_FINISH':
            id = data['id']
            if id not in self.makefiles:
                return

            entry = self.makefiles[id]
            entry['time_finish'] = time
            entry['time_wall'] = time - entry['time_create']

            self.timeline.append((time, 'MAKEFILE_FINISH', id))

        elif action == 'TARGET_BEGIN':
            id = data['id']
            parent_id = data['makefile_id']

            entry = {
                'parent_id':  parent_id,
                'time_start': time,
                'name':       data['target'],
                'vpath':      data['vpath'],
                'commands':   [],
            }

            self.targets[id] = entry

            if parent_id in self.makefiles:
                self.makefiles[parent_id]['targets'].append(id)

            self.timeline.append((time, 'TARGET_BEGIN', id))

        elif action == 'TARGET_FINISH':
            id = data['id']
            if id not in self.targets:
                return

            entry = self.targets[id]
            entry['time_finish'] = time
            entry['time_wall'] = time - entry['time_start']

            self.timeline.append((time, 'TARGET_FINISH', id))

        elif action == 'COMMAND_CREATE':
            id = data['id']
            parent_id = data['target_id']

            entry = {
                'parent_id':   parent_id,
                'time_create': time,
                'cmd':         data['cmd'],
                'location':    data['l'],
            }

            self.commands[id] = entry

            if parent_id in self.targets:
                self.targets[parent_id]['commands'].append(id)

            self.timeline.append((time, 'COMMAND_CREATE', id))

        elif action == 'JOB_START':
            id = data['id']
            if id not in self.commands:
                return

            entry = self.commands[id]

            type = data['type']
            entry['type'] = type
            entry['time_start'] = time

            if type == 'popen':
                entry['executable'] = data['executable']
                entry['argv']       = data['argv']
                entry['shell']      = data['shell']
            elif type == 'python':
                entry['module'] = data['module']
                entry['method'] = data['method']
                entry['argv']   = data['argv']
            else:
                raise Exception('unhandled job type: %s' % type)

            self.timeline.append((time, 'JOB_START', id))

        elif action == 'JOB_FINISH':
            id = data['id']
            if id not in self.commands:
                return

            entry = self.commands[id]
            entry['result'] = data['result']
            entry['time_end'] = time
            entry['time_wall'] = time - entry['time_start']

            self.timeline.append((time, 'JOB_FINISH', id))

    def printbsa(self, f):
        '''Print a BSA JSON blob of the timing info to a file handler.'''
        result = {
            'version': 100,
            'processes': {}
        }

        initial = True
        print >>f, '{ "version": 100, "processes": {'

        for item in self.timeline:
            if item[1] != 'PYMAKE_BEGIN' and item[1] != 'COMMAND_CREATE':
                continue

            record = {}
            if item[1] == 'PYMAKE_BEGIN':
                m = self.pymakes[item[2]]
                if 'time_finish' not in m:
                    continue

                record['start'] = int(1000 * (m['time_start'] - self.initial_time))
                record['end']   = int(1000 * (m['time_finish'] - self.initial_time))
                record['type']  = 'make'
                record['syscalls'] = [ { 'cmd': 'make.py -C %s' % m['dir'], 'duration': record['end'] - record['start'] } ]
            else:
                c = self.commands[item[2]]
                if 'time_end' not in c:
                    continue

                record['start'] = int(1000 * (c['time_start'] - self.initial_time))
                record['end']   = int(1000 * (c['time_end'] - self.initial_time))
                record['type']  = 'foo'
                record['syscalls'] = [ { 'cmd': c['cmd'], 'duration': record['end'] - record['start']} ]
                target_id = c['parent_id']
                if target_id in self.targets:
                    target = self.targets[target_id]
                    make_id = target['parent_id']
                    if make_id in self.makefiles:
                        makefile = self.makefiles[make_id]
                        record['parent_id'] = makefile['parent_id']
                    else:
                        record['parent_id'] = make_id
                else:
                    record['parent_id'] = target_id

            if not initial:
                print >>f, ',\n'

            print >>f, '"%s":' % item[2]
            json.dump(record, f)
            initial = False

        print >>f, '} }'



class TraceParser(object):
    '''Provides routines for analyzing trace files generated by
    running make.py --trace-log'''

    def __init__(self, path):
        '''Create a parser that operates on the path specified'''

        self.path = path

        with open(self.path, 'r') as f:
            l = f.readline()
            data = json.loads(l)

            assert data[0] == 'PYMAKE_BEGIN'

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

        for m in self.get_pymake_instances():
            for makefile_id, makefile in m['makefiles'].iteritems():
                dir = makefile['dir']

                for target_id, target in makefile['targets'].iteritems():
                    name = target['name']

                    fullname = None

                    if len(name) > 0 and name[0] == os.sep:
                        fullname = name
                    else:
                        fullname = os.path.normpath(os.path.join(dir, name))

                    if fullname in targets:
                        targets[fullname] += 1
                    else:
                        targets[fullname] = 1

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

    def get_pymake_instances(self):
        '''Obtains information about individual PyMake instances'''

        ctx = {
            'results':      [], # consolidated records
            'pymakes':      {}, # pymake id to dictionary
            'makefile_map': {}, # makefile id to pymake id
            'makefiles':    {}, # makefile id to dictionary
            'target_map':   {}, # target id to makefile id
            'targets':      {}, # target id to dictionary
            'command_map':  {}, # command id to target id
            'commands':     {}, # command id to dictionary
        }

        def callback(action, time, data, context):
            if action == 'PYMAKE_BEGIN':
                id = data['id']

                context['pymakes'][id] = {
                    'id':          id,
                    'dir':         data['dir'],
                    'targets':     data['targets'],
                    'time_start':  time,
                    'files':       data['makefiles'],
                    'makefiles':   {}
                }

            elif action == 'PYMAKE_FINISH':
                id = data['id']

                if id not in context['pymakes']:
                    return

                entry = context['pymakes'][id]
                entry['time_finish'] = time
                entry['wall_time'] = time - entry['time_start']

                del context['pymakes'][id]

                makefile_ids = []

                for make_id, pymake_id in context['makefile_map'].iteritems():
                    if id != pymake_id:
                        continue

                    makefile_ids.append(make_id)

                for make_id in makefile_ids:
                    del context['makefile_map'][make_id]

                    entry['makefiles'][make_id] = context['makefiles'][make_id]
                    del context['makefiles'][make_id]

                targets = {}

                for target_id, make_id in context['target_map'].iteritems():
                    if make_id in makefile_ids:
                        targets[target_id] = make_id

                for target_id, make_id in targets.iteritems():
                    del context['target_map'][target_id]

                    entry['makefiles'][make_id]['targets'][target_id] = context['targets'][target_id]
                    del context['targets'][target_id]

                commands = {}
                for command_id, target_id in context['command_map'].iteritems():
                    if target_id in targets.keys():
                        commands[command_id] = target_id

                for command_id, target_id in commands.iteritems():
                    del context['command_map'][command_id]

                    entry['makefiles'][targets[target_id]]['targets'][target_id]['commands'][command_id] = context['commands'][command_id]
                    del context['commands'][command_id]

                context['results'].append(entry)

            elif action == 'MAKEFILE_CREATE':
                entry = {
                    'targets': {},
                    'dir':     data['dir'],
                }

                id = data['id']
                context['makefile_map'][id] = data['context_id']
                context['makefiles'][id] = entry

            elif action == 'MAKEFILE_BEGIN':
                id = data['id']
                if id not in context['makefiles']:
                    return

                entry = context['makefiles'][id]
                entry['time_begin'] = time
                entry['dir']        = data['dir']
                entry['included']   = data['included']

            elif action == 'MAKEFILE_FINISH':
                id = data['id']
                if id not in context['makefiles']:
                    return

                entry = context['makefiles'][id]
                entry['time_finish'] = time

            elif action == 'TARGET_BEGIN':
                id = data['id']
                make_id = data['makefile_id']

                context['target_map'][id] = make_id
                context['targets'][id] = {
                    'time_start': time,
                    'name':       data['target'],
                    'vpath':      data['vpath'],
                    'commands':   {},
                }

            elif action == 'TARGET_FINISH':
                id = data['id']
                if id not in context['targets']:
                    return

                entry = context['targets'][id]
                entry['time_finish'] = time

            elif action == 'COMMAND_CREATE':
                id = data['id']
                target_id = data['target_id']

                context['command_map'][id] = target_id
                context['commands'][id] = {
                    'time_create': time,
                    'cmd':         data['cmd'],
                    'l':           data['l'],
                }

            elif action == 'JOB_START':
                id = data['id']
                if id not in context['commands']:
                    return

                entry = context['commands'][id]

                type = data['type']
                entry['type'] = type
                entry['time_start'] = time

                if type == 'popen':
                    entry['executable'] = data['executable']
                    entry['argv']       = data['argv']
                    entry['shell']      = data['shell']
                elif type == 'python':
                    entry['module'] = data['module']
                    entry['method'] = data['method']
                    entry['argv']   = data['argv']
                else:
                    raise Exception('unhandled job type: %s' % type)

            elif action == 'JOB_FINISH':
                id = data['id']
                if id not in context['commands']:
                    return

                entry = context['commands'][id]
                entry['result'] = data['result']
                entry['time_end'] = time
                entry['wall_time'] = time - entry['time_start']


        self.parse_file(callback, ctx)

        return ctx['results']

    def get_executed_commands(self):
        '''Obtains a list of commands that were invoked during make process'''

        commands = {
            'c': {},
            'l': []
        }

        def callback(action, time, data, context):
            if action == 'COMMAND_CREATE':
                id = data['id']
                context['c'][id] = {
                    'target': data['target_id'],
                    'l':      data['l'],
                    'cmd':    data['cmd'],
                }

            elif action == 'JOB_START':
                id = data['id']
                if id not in context['c']:
                    return

                entry = context['c'][id]
                type = data['type']
                entry['type'] = type
                entry['time_start'] = time

                if type == 'popen':
                    entry['executable'] = data['executable']
                    entry['argv']       = data['argv']
                    entry['shell']      = data['shell']
                elif type == 'python':
                    entry['module'] = data['module']
                    entry['method'] = data['method']
                    entry['argv']   = data['argv']
                else:
                    raise Exception('unhandled job type: %s' % type )

            elif action == 'JOB_FINISH':
                id = data['id']
                if id not in context['c']:
                    return

                entry = context['c'][id]

                entry['time_end'] = time
                entry['wall_time'] = time - entry['time_start']
                entry['result'] = data['result']

                context['l'].append(entry)
                del context['c'][id]

        self.parse_file(callback, commands)

        return commands['l']
