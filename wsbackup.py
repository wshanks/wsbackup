#!/usr/bin/env python2
"""
wsbackup_transfer.py: transfer files to a remote system using rsync based on
the settings defined in a yaml config file.
"""

import argparse
import datetime as dtime
import logging
import logging.handlers
import os
import re
import shlex
import shutil
import subprocess
import sys

import yaml

DATE_FORMAT = '%Y-%m-%d_%Hh%Mm%Ss'
# TODO: Use ssh-agent to limit number of connection attempts?

# TODO: Test pruning


def pid_running(pid):
    """ Check For the existence of a unix pid. """
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    else:
        return True


class WSBackupError(Exception):
    """
    Class for unexpected situations encountered when performing backup
    """
    pass


def num_eval(expr):
    """
    Evaluate numerical expression expr containing floats and * and / operators
    only
    """
    div_parts = expr.split('/')
    val = float(div_parts.pop(0))
    for d_part in div_parts:
        mult_parts = d_part.split('*')
        val = val / float(mult_parts.pop(0))
        for m_part in mult_parts:
            val = val * float(m_part)

    return val


def escape(path):
    """
    Escape path with "'s if it is not already escaped with them.
    """
    if not (path[0] == '"' and path[-1] == '"'):
        path = '"{}"'.format(path)
    return path


def logfile_config(logfile, backup_id, working_dir):
    """
    Configure log file settings, with reasonable defaults for missing values
    """
    default_fname = backup_id + '.log'
    defaults = {'path': os.path.join(working_dir, default_fname),
                'max_bytes': 1e6,
                'backup_count': 5,
                'mode': 'a',
                'copy_to_dest': False}
    if isinstance(logfile, str):
        if os.path.exists(logfile) and os.path.isdir(logfile):
            logfile = {'path': os.path.join(logfile, default_fname)}
        else:
            logfile = {'path': os.path.join(working_dir, logfile)}
    elif not isinstance(logfile, dict):
        logfile = {}

    for key in defaults:
        if key not in logfile:
            logfile[key] = defaults[key]

    if isinstance(logfile['max_bytes'], float):
        logfile['max_bytes'] = int(logfile['max_bytes'])
    else:
        logfile['max_bytes'] = int(num_eval(logfile['max_bytes']))

    return logfile


def add_out_format(rsync_opts):
    """Check that verbosity level is set but out-format is not set"""
    if any([opt
            for opt in rsync_opts
            if re.match('-v|--verbose', opt.strip())]):
        if not any([opt
                    for opt in rsync_opts
                    if re.match('--out-format', opt.strip())]):
            return True
    return False


def is_dry_run(rsync_opts):
    """Check that dry-run option is set"""
    return any([opt
                for opt in rsync_opts
                if re.match('-n|--dry-run', opt.strip())])


def merge_opts(opts, new_opts):
    """
    Merge new opts into opts.

    If an entry of new_opts is prefixed by "no" remove it from opts if it is
    there.
    """
    new_opts = [o for o in new_opts if re.match('-', o)]
    no_opts = [o[2:] for o in new_opts if re.match('no-', o)]
    for no_opt in no_opts:
        for opt in opts:
            if no_opt == opt or re.match(no_opt + ' ', opt):
                opts.remove(opt)
                break

    return opts + new_opts


class Backup(object):
    """
    Class defining methods for executing a backup and containing properties to
    track the backup state.
    """
    def __init__(self, config_path, rsync_opts=None):
        self.working_dir = os.path.dirname(os.path.abspath(config_path))
        self.pid = os.getpid()
        self.config = self.parse_config(config_path)

        if rsync_opts is not None:
            self.config['rsync_opts'] = merge_opts(self.config['rsync_opts'],
                                                   rsync_opts)

        self._setup_log()
        logging.info('Backup started with PID %(pid)s', {'pid': self.pid})

        self.check_lockfile()
        with open(self.config['lockfile'], 'w') as lockfile:
            lockfile.write(str(self.pid))

    def __enter__(self):
        """Enter function for use with with()"""
        return self

    # pylint: disable=redefined-builtin
    def __exit__(self, type, value, traceback):
        """Exit function for use with with()"""
        self.cleanup()

    # pylint: enable=redefined-builtin
    def _setup_log(self):
        """Initiate logging"""
        log_fmt = "%(asctime)s [%(levelname)-5.5s]  %(message)s"
        log_formatter = logging.Formatter(log_fmt,
                                          datefmt='%Y/%m/%d %I:%M:%S %p')
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        names = [h.name for h in root_logger.handlers]

        if 'logfile' not in names:
            file_handler = logging.handlers.RotatingFileHandler(
                self.config['logfile']['path'],
                mode=self.config['logfile']['mode'],
                maxBytes=self.config['logfile']['max_bytes'],
                backupCount=self.config['logfile']['backup_count'])
            file_handler.setFormatter(log_formatter)
            file_handler.set_name('logfile')
            root_logger.addHandler(file_handler)

        if 'stdout' not in names:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(log_formatter)
            console_handler.set_name('stdout')
            root_logger.addHandler(console_handler)

    def backup_error(self, msg):
        """Log error and raise exception"""
        logging.error(msg)
        raise WSBackupError(msg)

    def parse_config(self, config_file):
        """
        Parse config file into dictionary
        """
        with open(config_file) as yaml_config:
            config = yaml.safe_load(yaml_config)

        if not config.get('id'):
            config['id'] = 'wsbackup'

        config['logfile'] = logfile_config(config.get('logfile'),
                                           config['id'],
                                           self.working_dir)

        if not config.get('lockfile'):
            config['lockfile'] = os.path.join(self.working_dir,
                                              config['id'] + '.lck')

        if not config.get('excludes'):
            config['excludes'] = []
        xcl_default = os.path.join(self.working_dir,
                                   config['id'] + '.xcl')
        default_set = any([os.path.samefile(xcl, xcl_default)
                           for xcl
                           in config['excludes']])
        if os.path.exists(xcl_default) and not default_set:
            config['excludes'].append(xcl_default)

        # chmod: necessary for old backups to be deletable
        default_rsync_opts = ['--archive', '-hhh', '--delete', '--stats',
                              '--chmod=u+rw']
        if config.get('rsync_opts'):
            config['rsync_opts'] = merge_opts(default_rsync_opts,
                                              config['rsync_opts'])
        else:
            config['rsync_opts'] = default_rsync_opts

        if not config.get('aging_params'):
            config['aging_params'] = [
                [0.5/24, 2],
                [1, 14],
                [7, 60],
                [30, 730],
                [365, -1]]
        # Evaluate any numerical expressions
        for pidx, pair in enumerate(config['aging_params']):
            for vidx, val in enumerate(pair):
                if isinstance(val, str):
                    config['aging_params'][pidx][vidx] = num_eval(val)

        config['aging_params'] = [{'spacing': item[0], 'bound': item[1]}
                                  for item in config['aging_params']]

        remote = config.get('remote')
        if remote:
            if 'location' not in remote or 'host' not in remote:
                err_str = ('"remote" config setting must include host and '
                           'location.')
                self.backup_error(err_str)
            if remote['location'] not in ['src', 'dest']:
                err_str = ('"remote:location" config setting must be "src" or '
                           '"dest"')
                self.backup_error(err_str)
        else:
            config['remote'] = {'location': None, 'host': None}

        config['backup_time'] = None

        return config

    def check_lockfile(self):
        """
        Check for a lockfile from previous backup attempt
        """
        if os.path.exists(self.config['lockfile']):
            with open(self.config['lockfile'], 'r') as lockfile:
                lockpid = lockfile.readline().strip()
            if pid_running(lockpid):
                err_str = ('Lockfile for running process (PID: '
                           '{lockpid} found, backup stopped.')
                err_str = err_str.format(lockpid=lockpid)
                self.backup_error(err_str)
            else:
                log_str = ('Lockfile for ghost process (PID: %(lockpid)s) '
                           'found, continuing backup.')
                logging.info(log_str, {'lockpid': lockpid})

    def cleanup(self):
        """
        Clean up a failed backup.
        """
        if os.path.exists(self.config['lockfile']):
            os.remove(self.config['lockfile'])

    def transfer_log(self):
        """Transfer log file to remote destination"""
        if (self.config['remote']['location'] != 'dest' or
                not self.config['logfile']['copy_to_dest']):
            return

        log_base = self.config['logfile']['path']
        cmd_fmt = 'rsync {log} {host}:{dest}'
        cmd = cmd_fmt.format(log=escape(log_base),
                             host=self.config['remote']['host'],
                             dest=escape(self.config['destination']))
        self.exec_cmd(cmd, context='remote')
        idx = 1
        while True:
            path = '{base}.{idx}'.format(base=log_base, idx=idx)
            if os.path.exists(path):
                cmd = cmd_fmt.format(log=escape(path),
                                     host=self.config['remote']['host'],
                                     dest=escape(self.config['destination']))
                self.exec_cmd(cmd, context='remote')
                idx = idx + 1
            else:
                break

    def process_backup(self):
        """Main function for processing a backup request"""
        self.validate_host()
        files_transferred = self.transfer_files()
        if files_transferred:
            self.update_latest()
            self.prune_backup()
            logging.info('Backup finished')
            self.transfer_log()

        self.cleanup()

    def get_backup_list(self):
        """Get list of all backup directories"""
        if self.config['remote']['location'] == 'dest':
            cmd = 'ls {dest}'.format(dest=escape(self.config['destination']))
            backup_list = self.exec_cmd(cmd, context='dest', output='output')
            backup_list = backup_list.split('\n')
        else:
            backup_list = os.listdir(self.config['destination'])

        def valid_date(datestring):
            """Test string against DATE_FORMAT"""
            try:
                dtime.datetime.strptime(datestring, DATE_FORMAT)
                return True
            except ValueError:
                return False
        backup_list = [item for item in backup_list if valid_date(item)]
        return backup_list

    def sort_by_age(self, backup_list):
        """Sort backups into groups by age index"""
        # Sort oldest to newest
        backup_list.sort()

        # Get reference time for calculating backup age
        now = self.config.get('backup_time')
        if now:
            now = dtime.datetime.strptime(now, DATE_FORMAT)
        else:
            now = dtime.datetime.now()

        # Sort backups into appropriate age index
        aging_params = self.config['aging_params']
        backups = [[] for a in aging_params]
        deletions = []
        for date_str in backup_list:
            dt_obj = dtime.datetime.strptime(date_str, DATE_FORMAT)

            age_index = None
            for index, bound in enumerate(p['bound'] for p in aging_params):
                if now - dt_obj < dtime.timedelta(bound) or bound == -1:
                    age_index = index
                    break

            if age_index is None:
                deletions.append(date_str)
            else:
                backups[age_index].append({'date_str': date_str,
                                           'dt_obj': dt_obj})

        return (backups, deletions)

    def prune_backup(self):
        """
        Call function to prune old backups that are no longer needed.
        """
        # import pudb; pudb.set_trace()
        backup_list = self.get_backup_list()

        backups, deletions = self.sort_by_age(backup_list)

        # Loop through each index from oldest to newest backup. Whenever two
        # backups are found within the spacing for that age index, delete the
        # newer backup (except the newest overall with that age index).
        #
        # WARNING: be careful editing the logic here. It is very easy to create
        # something that seems reasonable but would delete many backups. For
        # example, if, when two backups are within a spacing, the newer backup
        # were kept instead of the older, then, if new backups were made more
        # frequently than the smallest spacing, the next newest backup would
        # always be deleted for being too close to the latest backup and there
        # would never be more than two backups in the first age index.
        for age_index, age_subset in enumerate(backups):
            if len(age_subset) < 3:
                continue
            spacing = self.config['aging_params'][age_index]['spacing']
            # Always keep newest backup with a given age index
            age_subset.pop()
            # Always keep oldest backup with a given age index.
            # Use it to start checking spacings between backups
            prev_backup = age_subset.pop(0)
            for backup in age_subset:
                current_spacing = backup['dt_obj'] - prev_backup['dt_obj']
                if current_spacing < dtime.timedelta(spacing):
                    deletions.append(backup['date_str'])
                else:
                    prev_backup = backup

        # Delete backups
        logging.info('Pruning the following backups: %(b_list)s',
                     {'b_list': ' '.join(deletions)})
        if not is_dry_run(self.config['rsync_opts']):
            self.remove_backups(deletions)

    def remove_backups(self, deletions):
        """Remove directories in deletions from destination"""
        remote = self.config['remote']
        if remote['location'] == 'dest':
            dirs = ' '.join('"{}"'.format(d) for d in deletions)
            cmd = 'cd {dest} && rm -rf {dirs}'
            cmd = cmd.format(dest=escape(self.config['destination']),
                             dirs=dirs)
            self.exec_cmd(cmd, context='dest')
        else:
            for backup in deletions:
                shutil.rmtree(os.path.join(self.config['destination'], backup))

    def transfer_files(self):
        """
        Perform backup transfer of files
        """
        remote = self.config['remote']
        sources = [escape(s) for s in self.config['sources']]
        dest = escape(self.config['destination'])
        if remote['location'] is not None:
            if remote['location'] == 'src':
                sources = ['{host}:' + src for src in sources]
            else:
                dest = '{host}:' + dest

        rsync_cmd = ['rsync']

        # Link against "latest" backup directory if it exists
        latest_exists = False
        latest = os.path.join(self.config['destination'], 'latest')
        if remote['location'] == 'dest':
            latest = escape(latest)
            cmd = 'test -e {latest}'.format(latest=latest)
            latest_exists = (0 == self.exec_cmd(cmd,
                                                context='dest',
                                                output='exit_code'))
        else:
            latest_exists = os.path.exists(latest)
        if latest_exists:
            rsync_cmd.append('--link-dest=../latest')

        log_fmt = '%t [%p] %o %f (%b / %l)'
        lfile = escape(self.config['logfile']['path'])
        rsync_cmd.append('--log-file={lfile}'.format(lfile=lfile))
        new_opt = '--log-file-format="{log_fmt}"'.format(log_fmt=log_fmt)
        rsync_cmd.append(new_opt)
        if add_out_format(self.config['rsync_opts']):
            new_opt = '--out-format="{log_fmt}"'.format(log_fmt=log_fmt)
            rsync_cmd.append(new_opt)
        if self.config['rsync_opts'] is not None:
            rsync_cmd = rsync_cmd + self.config['rsync_opts']

        for xcl in self.config['excludes']:
            rsync_cmd.append('--exclude-from "{exclude}"'.format(exclude=xcl))

        rsync_cmd = rsync_cmd + sources
        rsync_cmd.append(os.path.join(dest, 'incomplete'))
        cmd = ' '.join(rsync_cmd)
        self.exec_cmd(cmd, context='src-dest')

        return not is_dry_run(self.config['rsync_opts'])

    def update_latest(self):
        """
        Update the "latest" symlink to point to the new backup directory.
        """
        cmd = "mv {target_inc} {target_date}"
        dest = self.config['destination']
        target_inc = os.path.join(dest, 'incomplete')
        date_str = dtime.datetime.now().strftime(DATE_FORMAT)
        self.config['backup_time'] = date_str
        target_date = os.path.join(dest, date_str)
        cmd = cmd.format(target_inc=escape(target_inc),
                         target_date=escape(target_date))
        self.exec_cmd(cmd, context='dest')

        # symlink backup to latest
        cmd = ("rm -f {target_latest}")
        cmd = cmd.format(target_date=date_str,
                         target_latest=escape(os.path.join(dest, 'latest')))
        self.exec_cmd(cmd, context='dest')

        cmd = ("ln -s {target_date} {target_latest}")
        cmd = cmd.format(target_date=escape(date_str),
                         target_latest=escape(os.path.join(dest, 'latest')))
        self.exec_cmd(cmd, context='dest')

    def validate_host(self):
        """
        Run through a series of checks on a remote host to make sure connection
        settings will work for transferring files for the backup.
        """
        remote = self.config.get('remote', None)
        if remote['location'] is None:
            return

        # Test connectivity
        cmd = ("ssh {host} -q -q -o 'BatchMode=yes' -o 'ConnectTimeout 10' "
               "exit &> /dev/null")
        self.exec_cmd(cmd, context='remote',
                      err_str='SSH connection {host} failed.')

        # Check paths exist
        if remote['location'] == 'src':
            paths = self.config['sources']
        else:
            paths = [self.config['destination']]

        for path in paths:
            cmd = "ssh {{host}} [ -d '{target}' ]".format(target=escape(path))
            err_str = ('Target {target} does not exist on '
                       '{{host}}.').format(target=path)
            self.exec_cmd(cmd, context='remote', err_str=err_str)

    def exec_cmd(self, cmd, output=None, context='local', err_str=None):
        """
        Execute shell command, over ssh if necessary

        context: remote, src, dest, local, rsync

        types of commands:
        context-less cmd that can be called on local or remote depending on if
            src or dest is remote
        rsync command that needs to insert host: in front of src or dest if one
            of them is remote
        ssh test command that should only be checked on remote
        """
        remote = self.config['remote']
        if (context == 'src' and remote['location'] == 'src' or
                context == 'dest' and remote['location'] == 'dest' or
                context == 'src-dest' and remote['location'] or
                context == 'remote'):
            loc = 'remote'
        else:
            loc = 'local'

        if loc == 'remote' and context in ['src', 'dest']:
            cmd = 'ssh {host} "{cmd}"'.format(host=remote['host'],
                                              cmd=cmd)
        elif loc == 'remote':
            cmd = cmd.format(host=remote['host'])

        if not err_str:
            err_str = 'Error executing command: {}'.format(cmd)

        if re.search('{host}', err_str):
            err_str = err_str.format(host=remote['host'])

        try:
            if output == 'output':
                output = subprocess.check_output(shlex.split(cmd))
            elif output == 'exit_code':
                output = subprocess.call(shlex.split(cmd))
            else:
                subprocess.check_call(shlex.split(cmd))
        except subprocess.CalledProcessError:
            self.backup_error(err_str)

        return output


def main(args):
    """
    Main script function
    """
    with Backup(args['config'], rsync_opts=args['rsync_opt']) as backup_state:
        backup_state.process_backup()


if __name__ == '__main__':
    # pylint: disable=invalid-name
    parser = argparse.ArgumentParser('Backup files via rsync')
    # pylint: enable=invalid-name
    parser.add_argument('--config', '-c', required=True,
                        help='Path to yaml configuration file defining backup '
                        'procedure.')
    parser.add_argument('--rsync-opt', '-r', action='append',
                        help=('Arguments passed to rsync (be sure to use '
                              '-r="--option" syntax to avoid --option being '
                              'consumed by this command).'))
    main(vars(parser.parse_args()))
