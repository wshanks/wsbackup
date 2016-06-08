#!/usr/bin/env python2
"""
wsbackup_transfer.py: transfer files to a remote system using rsync based on
the settings defined in a yaml config file.
"""

import argparse
from datetime import datetime as dtime
import os
import os.path
import shlex
import subprocess

import yaml

DATE_FORMAT = '%Y-%m-%d_%Hh%Mm%Ss'


def check_pid(pid):
    """ Check For the existence of a unix pid. """
    try:
        os.kill(pid, 0)
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

    if not config.get('logfile'):
        config['logfile'] = os.path.join(backup_state.working_dir,
                                         config['id'] + '.log')

    if not config.get('excludes'):
        config['excludes'] = []
    xcl_default = os.path.join(backup_state.working_dir,
                               config['id'] + '.xcl')
    default_set = any([os.path.samefile(xcl, xcl_default)
                       for xcl
                       in config['excludes']])
    if os.path.exists(xcl_default) and not default_set:
        config['excludes'].append(xcl_default)

    if config.get('remote_host'):
        if config.get('remote_sources'):
            if config.get('remote_dest'):
                WSBackupError(('ERROR: remote_sources and remote_dest can not '
                               'both be true.'))
        else:
            config['remote_dest'] = True

    return config


def validate_host(backup_state):
    """
    Run through a series of checks on a remote host to make sure connection
    settings will work for transferring files for the backup.
    """
    config = backup_state.config
    lockfile = backup_state.lockfile
    logfile = backup_state.logfile
    pid = backup_state.pid

    host = config.get('remote_host', None)
    if host is None:
        return

    # Test connectivity
    ssh_test = ("ssh -q -q -o 'BatchMode=yes' -o 'ConnectTimeout 10' "
                "{ssh} exit &> /dev/null").format(ssh=host)
    try:
        subprocess.check_call(shlex.split(ssh_test))
    except subprocess.CalledProcessError:
        log_str = '{date} [{pid}] SSH connection {host} failed.'
        log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                 pid=pid,
                                 host=host)
        logfile.write(log_str)
        lockfile.close()
        os.remove(config['lockfile'])
        raise WSBackupError(log_str)

    # Check paths exist
    if config.get('remote_sources', False):
        paths = config['sources']
    else:
        paths = [config['destination']]

    for path in paths:
        ssh_test = '''ssh {host} "[ -d '{target}' ]"'''
        ssh_test = ssh_test.format(host=host, target=path)
        try:
            subprocess.check_call(shlex.split(ssh_test))
        except subprocess.CalledProcessError:
            log_str = ('{date} [{pid}] Target {target} does not exist on '
                       '{host}. Backup stopped.')
            log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=pid,
                                     target=path,
                                     host=host)
            logfile.write(log_str)
            lockfile.close()
            os.remove(config['lockfile'])
            raise WSBackupError(log_str)


class Backup(object):
    """
    Class defining methods for executing a backup and containing properties to
    track the backup state.
    """
    def __init__(self, config_path):
        self.working_dir = os.path.pardir(config_path)
        self.pid = os.getpid()
        self.config = parse_config(config_path, self)

        date_str = dtime.now().strftime(DATE_FORMAT)
        self.logfile = open(self.config['logfile'], 'a')
        log_str = '{date}: [{pid}]  -- backup started'.format(date=date_str,
                                                              pid=self.pid)
        self.logfile.write(log_str)

        check_lockfile(self)
        self.lockfile = open(self.config['lockfile'], 'w')
        self.lockfile.write(str(self.pid))

    def cleanup(self):
        """
        Clean up a failed backup.
        """
        self.logfile.close()
        self.lockfile.close()
        os.remove(self.config['lockfile'])


def check_lockfile(backup_state):
    """
    Check for a lockfile from previous backup attempt
    """
    if os.path.exists(backup_state.config['lockfile']):
        lockfile = open(backup_state.config['lockfile'], 'r')
        lockpid = lockfile.readline().trim()
        if check_pid(lockpid):
            log_str = ('{date} [{pid}] Lockfile for ghost process (PID: '
                       '{lockpid} found, continuing backup.')
            log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=backup_state.pid,
                                     lockpid=lockpid)
            backup_state.logfile.write(log_str)
        else:
            err_str = ['{date} [{pid}] Lockfile for running process (PID: ',
                       '{lockpid} found, backup stopped.']
            err_str = ''.join(err_str)
            err_str = err_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=backup_state.pid,
                                     lockpid=lockpid)
            raise WSBackupError(err_str)
        lockfile.close()


def transfer_files(backup_state):
    """
    Perform backup transfer of files
    """
    host = backup_state.config.get('remote_host', None)
    sources = backup_state.config['sources']
    dest = backup_state.config['destination']
    if host is not None:
        if backup_state.config.get('remote_sources', False):
            sources = [host + ':' + src for src in sources]
        else:
            dest = host + ':' + dest

    rsync_cmd = [('rsync --archive --compress --human-readable --delete '
                  '--chmod=ug+w'
                  '--exclude-from "{excludes}"')]
    latest = os.path.join(backup_state.config['destination'], 'latest')
    rsync_cmd.append('--link-dest={latest}'.format(latest=latest))

    for xcl in backup_state.config['excludes']:
        rsync_cmd.append('--exclude-from "{exclude}"'.format(exclude=xcl))

    rsync_cmd = rsync_cmd + sources
    rsync_cmd.append(os.path.join(dest, 'incomplete'))
    rsync_cmd = ' '.join(rsync_cmd)
    subprocess.check_call(shlex.split(rsync_cmd))


def update_latest(backup_state):
    """
    Update the "latest" symlink to point to the new backup directory.
    """
    cmd = "mv '{target_inc}' '{target_date}'"
    dest = backup_state.config['destination']
    target_inc = os.path.join(dest, 'incomplete')
    target_date = os.path.join(dest,
                               dtime.now().strftime(DATE_FORMAT))
    cmd = cmd.format(target_inc=target_inc, target_date=target_date)
    host = backup_state.config['remote_host']
    if host:
        cmd = 'ssh {host} "{cmd}"'.format(host=host, cmd=cmd)
    # TODO: Make wrapper around subprocess shlex for ssh calls that could fail
    # TODO: make wrapper around remote commands that checks for host and uses
    # ssh when necessary
    subprocess.check_call(shlex.split(cmd))

    # symlink backup to latest
    cmd = ("ln -fs '{target_date}' '{target_latest}'")
    cmd = cmd.format(target_date=os.path.basename(target_date),
                     target_latest=os.path.join(dest, 'latest'))
    if host:
        cmd = 'ssh {host} "{cmd}"'.format(host=host, cmd=cmd)
    subprocess.check_call(shlex.split(cmd))


def prune_backup(backup_state):
    """
    Call function to prune old backups that are no longer needed.
    """
    # TODO: Make all the transfer commands work for ssh or local directory
    host = backup_state.config['remote_host']
    if host:
        rsync_cmd = 'rsync --compress "{f_prune}" "{host}:{dest}"'
        f_prune = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                               'wsbackup_prune.py')
        rsync_cmd = rsync_cmd.format(f_prune=f_prune,
                                     host=host,
                                     dest=backup_state.config['destination'])
        subprocess.check_call(shlex.split(rsync_cmd))


def process_backup(backup_state):
    """Main function for processing a backup request"""
    transfer_files(backup_state)

    update_latest(backup_state)

    prune_backup(backup_state)


def main(args):
    """
    Main script function
    """
    backup_state = Backup(args['config'])

    validate_host(backup_state)

    process_backup(backup_state)

    # log completion
    log_str = '{date} [{pid}] -- backup finished'
    log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                             pid=backup_state.pid)
    backup_state.logfile.write(log_str)

    backup_state.cleanup()


if __name__ == '__main__':
    # pylint: disable=invalid-name
    parser = argparse.ArgumentParser('Backup files via rsync')
    # pylint: enable=invalid-name
    parser.add_argument('--config', '-c', nargs=1, required=True,
                        help='Path to yaml configuration file defining backup '
                        'procedure.')
    main(vars(parser.parse_args()))
