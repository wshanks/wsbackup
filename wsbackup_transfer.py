#!/usr/bin/env python2
"""
wsbackup_transfer.py: transfer files to a remote system using rsync based on
the settings defined in a yaml config file.
"""

import argparse
from datetime import datetime as dtime
import logging
import os
import os.path
import re
import shlex
import subprocess
import sys

import yaml

DATE_FORMAT = '%Y-%m-%d_%Hh%Mm%Ss'
# TODO: Test remote source transfers
# TODO: Test remote dest transfers
# TODO: option to transfer logfile to remote host
# TODO: provide sample config file for logrotate
# TODO: Make cmd class that knows src/dest/host and when to wrap commands in
#       an ssh call
# TODO: Use ssh-agent to limit number of connection attempts?


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


def parse_config(config_file, backup_state):
    """
    Parse config file into dictionary
    """
    with open(config_file) as yaml_config:
        config = yaml.safe_load(yaml_config)

    if not config.get('id'):
        config['id'] = 'wsbackup'

    if not config.get('logfile'):
        config['logfile'] = os.path.join(backup_state.working_dir,
                                         config['id'] + '.log')
    if not config.get('overwrite_logfile'):
        config['overwrite_logfile'] = False

    if not config.get('lockfile'):
        config['lockfile'] = os.path.join(backup_state.working_dir,
                                          config['id'] + '.lck')

    if not config.get('excludes'):
        config['excludes'] = []
    xcl_default = os.path.join(backup_state.working_dir,
                               config['id'] + '.xcl')
    default_set = any([os.path.samefile(xcl, xcl_default)
                       for xcl
                       in config['excludes']])
    if os.path.exists(xcl_default) and not default_set:
        config['excludes'].append(xcl_default)

    # TODO: Make it possible to remove the default options
    default_rsync_opts = ['--archive', '--compress', '--human-readable',
                          '--delete', '--chmod=ug+w', '--stats']
    if config.get('rsync_opts'):
        config['rsync_opts'] = config['rsync_opts'] + default_rsync_opts
    else:
        config['rsync_opts'] = default_rsync_opts

    remote = config.get('remote')
    if remote:
        if 'location' not in remote or 'host' not in remote:
            WSBackupError(('"remote" config setting must include host and '
                           'location.'))
        if remote['location'] not in ['src', 'dest']:
            WSBackupError(('"remote:location" config setting must be "src" or '
                           '"dest"'))

    return config


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


class Backup(object):
    """
    Class defining methods for executing a backup and containing properties to
    track the backup state.
    """
    def __init__(self, config_path, rsync_opts=None):
        self.working_dir = os.path.dirname(os.path.abspath(config_path))
        self.pid = os.getpid()
        self.config = parse_config(config_path, self)

        if rsync_opts is not None:
            self.config['rsync_opts'] = self.config['rsync_opts'] + rsync_opts

        self._setup_log()
        logging.info('Backup started with PID %(pid)s', {'pid': self.pid})

        self.check_lockfile()
        with open(self.config['lockfile'], 'w') as lockfile:
            lockfile.write(str(self.pid))

    def _setup_log(self):
        """Initiate logging"""
        log_fmt = "%(asctime)s [%(levelname)-5.5s]  %(message)s"
        log_formatter = logging.Formatter(log_fmt,
                                          datefmt='%Y/%m/%d %I:%M:%S %p')
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if self.config['overwrite_logfile']:
            mode = 'w'
        else:
            mode = 'a'
        file_handler = logging.FileHandler(self.config['logfile'], mode=mode)
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)

    def check_lockfile(self):
        """
        Check for a lockfile from previous backup attempt
        """
        if os.path.exists(self.config['lockfile']):
            with open(self.config['lockfile'], 'r') as lockfile:
                lockpid = lockfile.readline().strip()
            if pid_running(lockpid):
                err_str = ('Lockfile for running process (PID: '
                           '%(lockpid)s found, backup stopped.')
                logging.critical(err_str, {'lockpid': lockpid})
                raise WSBackupError(err_str, {'lockpid': lockpid})
            else:
                log_str = ('Lockfile for ghost process (PID: %(lockpid)s) '
                           'found, continuing backup.')
                logging.info(log_str, {'lockpid': lockpid})

    def cleanup(self):
        """
        Clean up a failed backup.
        """
        os.remove(self.config['lockfile'])

    def process_backup(self):
        """Main function for processing a backup request"""
        self.validate_host()
        files_transferred = self.transfer_files()
        if files_transferred:
            self.update_latest()
            self.prune_backup()

        logging.info('Backup finished')
        self.cleanup()

    def prune_backup(self):
        """
        Call function to prune old backups that are no longer needed.
        """
        # TODO: Actually run the backup pruning function
        remote = self.config.get('remote', {})
        host = remote.get('host', None)
        if host:
            rsync_cmd = 'rsync --compress "{f_prune}" "{host}:{dest}"'
            f_prune = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   'wsbackup_prune.py')
            rsync_cmd = rsync_cmd.format(f_prune=f_prune,
                                         host=host,
                                         dest=self.config['destination'])
            subprocess.check_call(shlex.split(rsync_cmd))

    def transfer_files(self):
        """
        Perform backup transfer of files
        """
        remote = self.config.get('remote', {})
        host = remote.get('host', None)
        sources = self.config['sources']
        dest = self.config['destination']
        if host is not None:
            if remote['location'] == 'src':
                sources = [host + ':' + src for src in sources]
            else:
                dest = host + ':' + dest

        rsync_cmd = [('rsync')]

        # Link against "latest" backup directory if it exists
        latest_exists = False
        latest = os.path.join(dest, 'latest')
        if host and remote['location'] == 'dest':
            ssh_cmd = 'ssh {host} "test -e {latest}"'.format(host=host,
                                                             latest=latest)
            latest_exists = subprocess.call(ssh_cmd) == 0
        else:
            latest_exists = os.path.exists(latest)
        if latest_exists:
            rsync_cmd.append('--link-dest=../latest')

        log_fmt = '%t [%p] %o %f (%b / %l)'
        lfile = self.config['logfile']
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
        rsync_cmd = ' '.join(rsync_cmd)
        subprocess.check_call(shlex.split(rsync_cmd))

        return not is_dry_run(self.config['rsync_opts'])

    def update_latest(self):
        """
        Update the "latest" symlink to point to the new backup directory.
        """
        cmd = "mv '{target_inc}' '{target_date}'"
        dest = self.config['destination']
        target_inc = os.path.join(dest, 'incomplete')
        date_str = dtime.now().strftime(DATE_FORMAT)
        target_date = os.path.join(dest, date_str)
        cmd = cmd.format(target_inc=target_inc, target_date=target_date)
        remote = self.config.get('remote', {})
        host = remote.get('host', None)
        if host:
            cmd = 'ssh {host} "{cmd}"'.format(host=host, cmd=cmd)
        subprocess.check_call(shlex.split(cmd))

        # symlink backup to latest
        cmd1 = ("rm -f '{target_latest}'")
        cmd2 = ("ln -s '{target_date}' '{target_latest}'")
        cmd1 = cmd1.format(target_latest=os.path.join(dest, 'latest'))
        cmd2 = cmd2.format(target_date=date_str,
                           target_latest=os.path.join(dest, 'latest'))
        if host:
            cmd1 = 'ssh {host} "{cmd}"'.format(host=host, cmd=cmd1)
            cmd2 = 'ssh {host} "{cmd}"'.format(host=host, cmd=cmd2)
        subprocess.check_call(shlex.split(cmd1))
        subprocess.check_call(shlex.split(cmd2))

    def validate_host(self):
        """
        Run through a series of checks on a remote host to make sure connection
        settings will work for transferring files for the backup.
        """
        remote = self.config.get('remote', {})
        host = remote.get('host', None)
        if host is None:
            return

        # Test connectivity
        ssh_test = ("ssh -q -q -o 'BatchMode=yes' -o 'ConnectTimeout 10' "
                    "{ssh} exit &> /dev/null").format(ssh=host)
        try:
            subprocess.check_call(shlex.split(ssh_test))
        except subprocess.CalledProcessError:
            logging.critical('SSH connection %(host)s failed.', {'host': host})
            self.cleanup()
            raise WSBackupError('SSH connection %(host)s failed.',
                                {'host': host})

        # Check paths exist
        if remote['location'] == 'src':
            paths = self.config['sources']
        else:
            paths = [self.config['destination']]

        for path in paths:
            ssh_test = '''ssh {host} "[ -d '{target}' ]"'''
            ssh_test = ssh_test.format(host=host, target=path)
            try:
                subprocess.check_call(shlex.split(ssh_test))
            except subprocess.CalledProcessError:
                log_str = ('Target {target} does not exist on '
                           '{host}. Backup stopped.')
                logging.critical(log_str, {'target': path, 'host': host})
                self.cleanup()
                raise WSBackupError(log_str, {'target': path, 'host': host})


def main(args):
    """
    Main script function
    """
    backup_state = Backup(args['config'], rsync_opts=args['rsync_opt'])
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
