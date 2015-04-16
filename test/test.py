#!/usr/bin/env python
import os
import argparse

rm -r a{1,2,3}
mkdir -p a{1,2,3}/b{1,2,3}
touch a1/b1/c11.txt
touch a1/b.txt
touch a2/b1/c21.txt
touch a3/b3/c33.txt

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Run test function')
