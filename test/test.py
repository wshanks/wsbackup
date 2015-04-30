#!/usr/bin/env python
"""Create test data for wsbackup_transfer.py"""
import argparse
from calendar import timegm
import os
import shutil


def get_time(depth, maxdepth):
    """Calculate time for given depth and maxdepth"""
    shift = int((maxdepth - depth)/2)
    tval = timegm((2012, 1, 1, 0, 0, 0))
    tval = tval + depth*(31*24*3600)
    tval = tval + shift*(24*3600)
    return tval


def create_file(root, depth, index, maxdepth):
    """Create test data file"""
    fname = 'f{dep}_{idx}.txt'.format(dep=depth, idx=index)
    fpath = os.path.join(root, fname)
    with open(fpath, 'w') as tfile:
        data_str = 'This file is file {idx} in a directory at depth {dep}'
        data_str = data_str.format(idx=index, dep=depth)
        data = [data_str]*(index+1)*100
        data = '\n'.join(data)
        print(data, file=tfile)

    os.utime(fpath, 2*(get_time(depth, maxdepth),))


def create_src(root, depth, maxdepth):
    """Create source dirs"""
    if depth > maxdepth:
        return

    for idx in range(depth+1):
        new_dir = os.path.join(root, 'd{dep}_{idx}'.format(dep=depth, idx=idx))
        if not os.path.exists(new_dir):
            os.mkdir(new_dir)
        for idx2 in range(depth):
            create_file(new_dir, depth, idx2, maxdepth)

        create_src(new_dir, depth+1, maxdepth)
        os.utime(new_dir, 2*(get_time(depth, maxdepth),))


def clean_dir(root):
    """Remove all contents from root"""
    for fname in os.listdir(root):
        fpath = os.path.join(root, fname)
        if os.path.isfile(fpath) or os.path.islink(fpath):
            os.remove(fpath)
        elif os.path.isdir(fpath):
            shutil.rmtree(fpath)


def main(args):
    """ Main function"""
    if not os.path.exists(args['src']):
        os.makedirs(args['src'])
    else:
        clean_dir(args['src'])
    create_src(args['src'], 0, args['iterations'])

    if not os.path.exists(args['dest']):
        os.makedirs(args['dest'])
    elif args['clean']:
        clean_dir(args['dest'])


if __name__ == '__main__':
    PARSER = argparse.ArgumentParser('Create test files')
    PARSER.add_argument('--iterations', '-i', default=1, type=int,
                        help='File creations to perform')
    PARSER.add_argument('--clean', '-c', action='store_true',
                        help='Clean dest folder')
    PARSER.add_argument('src', type=str, default='src', nargs='?',
                        help='Source directory')
    PARSER.add_argument('dest', type=str, default='dest', nargs='?',
                        help='Destination directory')
    main(vars(PARSER.parse_args()))
