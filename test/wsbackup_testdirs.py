#!/usr/bin/python
# Script to create backup folders for testing wsbackup_prune.py

import os
import datetime as dt

spacing = 0.5 # hours
oldest = 2000 # days
dtFormat = '%Y-%m-%d_%Hh%Mm%Ss'

# Convert spacing to days
spacing = spacing / 24

ages = [-x*spacing for x in range(0,int(oldest/spacing))]

now = dt.datetime.now()

for age in ages:
    date = now + dt.timedelta(age)
    os.mkdir(date.strftime(dtFormat))
