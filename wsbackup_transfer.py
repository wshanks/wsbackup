#!/usr/bin/env python2
"""
wsbackup_transfer.py: transfer files to a remote system using rsync based on
the settings defined in a yaml config file.
"""

import argparse
import datetime.datetime as dtime
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


def parse_config(config_file):
    """
    Parse config file into dictionary
    """
    with open(config_file) as yaml_config:
        config = yaml.safe_load(yaml_config)

    return config


def main(args):
    """
    Main script function
    """
    config = parse_config(args['config'])

    date_str = dtime.now().strftime(DATE_FORMAT)
    pid = os.getpid()

    logfile = open(config['logfile'], 'a')
    logfile.write('{date}: [{pid}]  -- backup started'.format(date=date_str,
                                                              pid=pid))

    if os.path.exists(config['lockfile']):
        lockfile = open(config['lockfile'], 'r')
        lockpid = lockfile.readline().trim()
        if check_pid(lockpid):
            log_str = ('{date} [{pid}] Lockfile for ghost process (PID: '
                       '{lockpid} found, continuing backup.')
            log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=pid,
                                     lockpid=lockpid)
            logfile.write(log_str)
        else:
            err_str = ['{date} [{pid}] Lockfile for running process (PID: ',
                       '{lockpid} found, backup stopped.']
            err_str = ''.join(err_str)
            err_str = err_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=pid,
                                     lockpid=lockpid)
            raise WSBackupError(err_str)
        lockfile.close()

    lockfile = open(config['lockfile'], 'w')
    lockfile.write(str(pid))

    if ':' in config['target']:
        ssh_connect = config['target'].split(':')[0]
        ssh_dir = config['target'].split(':')[1]
        ssh_test = ("ssh -q -q -o 'BatchMode=yes' -o 'ConnectTimeout 10' "
                    "{ssh} exit &> /dev/null").format(ssh=ssh_connect)
        try:
            subprocess.check_call(shlex.split(ssh_test))
        except subprocess.CalledProcessError:
            log_str = '{date} [{pid}] SSH connection {ssh} failed.'
            log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=pid,
                                     ssh=ssh_connect)
            logfile.write(log_str)
            lockfile.close()
            os.remove(config['lockfile'])
            raise WSBackupError(log_str)

        ssh_test = '''ssh {ssh} "[ -d '{target}' ]"'''
        ssh_test = ssh_test.format(ssh=ssh_connect, target=ssh_dir)
        try:
            subprocess.check_call(shlex.split(ssh_test))
        except subprocess.CalledProcessError:
            log_str = ('{date} [{pid}] Target {target} does not exist on '
                       '{ssh}. Backup stopped.')
            log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                                     pid=pid,
                                     target=ssh_dir,
                                     ssh=ssh_connect)
            logfile.write(log_str)
            lockfile.close()
            os.remove(config['lockfile'])
            raise WSBackupError(log_str)
    else:
        ssh_dir = config['target']

    # Run rsync backup
    # TODO: rsync command does not work yet
    # excludes = config['excludes']
    rsync_cmd = ('rsync --archive --compress --human-readable --delete '
                 '--chmod=ug+w --link-dest={target_latest} '
                 '--exclude-form "{excludes}"')
    rsync_cmd = [rsync_cmd]
    for src in config['sources']:
        rsync_cmd.append('"{src}"'.format(src=src))
    rsync_cmd.append('{ssh}:{ssh_dir}'.format(ssh=ssh_connect,
                                              ssh_dir=ssh_dir))
    rsync_cmd = ' '.join(rsync_cmd)
    subprocess.check_call(shlex.split(rsync_cmd))
    # mv backup to dated folder
    ssh_cmd = '''ssh {ssh} "mv '{target_inc}' 'target_date}'"'''
    target_date = os.path.join(ssh_dir, dtime.now().strftime(DATE_FORMAT))
    ssh_cmd = ssh_cmd.format(ssh=ssh_connect,
                             target_inc=os.path.join(ssh_dir, 'incomplete'),
                             target_date=target_date)
    # TODO: Make wrapper around subprocess shlex for ssh calls that could fail
    subprocess.check_call(shlex.split(ssh_cmd))
    # symlink backup to latest
    ssh_cmd = ('''ssh {ssh} "rm -f '{target_latest}' && '''
               '''ln -s '{target_date}' '{target_latest}'"''')
    ssh_cmd = ssh_cmd.format(ssh=ssh_connect,
                             target_date=target_date,
                             target_latest=os.path.join(ssh_dir, 'latest'))
    subprocess.check_call(shlex.split(ssh_cmd))

    # transfer and run prune script
    # TODO: Make all the transfer commands work for ssh or local directory
    rsync_cmd = 'rsync --compress "{f_prune}" "{ssh}:{ssh_dir}"'
    f_prune = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           'wsbackup_prune.py')
    rsync_cmd = rsync_cmd.format(f_prune=f_prune,
                                 ssh=ssh_connect,
                                 ssh_dir=ssh_dir)
    subprocess.check_call(shlex.split(ssh_cmd))
    # log completion
    log_str = '{date} [{pid}] -- backup finished'
    log_str = log_str.format(date=dtime.now().strftime(DATE_FORMAT),
                             pid=pid)
    logfile.write(log_str)
    logfile.close()

    os.remove(config['lockfile'])
    lockfile.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Backup files via rsync')
    parser.add_argument('--config', '-c', nargs=1, required=True,
                        help='Path to yaml configuration file defining backup '
                        'procedure.')
    main(vars(parser.parse_args()))
