#!/usr/bin/python
# --------------------------------------
#
#     Title: Timemachine backup
#    Author: Will Shanks
#            
#  Based on: Mondane Woodwork's Timemachine backup which is based on and available at
#            Linux backups like Time Machine with rsync hard links
#            http://www.jan-muennich.de/linux-backups-time-machine-rsyn
#
#            which, in turn, was based on
#            
#            Time Machine for every Unix out there
#            http://blog.interlinked.org/tutorials/rsync_time_machine.html
#            Addendum to "Time Machine for every Unix out there"
#            http://blog.interlinked.org/tutorials/rsync_addendum.yaml.html
#
#      File: wsbackup_prune.py
#   Created: 31 December 2012
#   Current: 31 December 2012
#
#   Purpose: Delete older backups created by wsbackup_transfer.sh once they reach a 
#            certain age, such that there are hourly backups for two days, daily backups 
#            for two weeks, weekly backups for two months, etc.  Deletes backups in the 
#            working directory (i.e. the directory that Python is called from, not 
#            necessarily the directory that the script is stored in).
#
# --------------------------------------
#
# History:
#
# 30 December 2012: - first version
#
# --------------------------------------

#############################
# User adjustable settings
#############################

# Lower bounds for classifying [hourly, daily, weekly, monthly, yearly] backups in days
bounds=[0, 2, 14, 60, 730]
# Spacings between [hourly, daily, weekly, monthly, yearly] backups in days
spacings=[1.0/24, 1, 7, 30, 365]
# Shrink spacings by 10 minutes so that e.g. daily backups aren't occurring right on the 
# border between when backups are and aren't deleted.
spacings=[x - (10.0/60)/24 for x in spacings]

# Backup naming format
# Format is 'ccyy-mm-dd_HHhMMmSSs' where ccyy is the four digit year, mm is the two-digit
# month, dd is the two digit day, HH is the two-digit hour, MM is the two digit minute, 
# and SS is the two digit second of the date/time of the backup.
#
# Format for glob
globFormat = '[0-9][0-9][0-9][0-9]-[0-9][0-9]-'
globFormat += '[0-9][0-9]_[0-9][0-9]h[0-9][0-9]m[0-9][0-9]s'
# Format for datetime
dtFormat = '%Y-%m-%d_%Hh%Mm%Ss'

#############################
# Start script
#############################

import glob, shutil
import datetime as dt

# Reference time to calculate age of backups from their dates
now = dt.datetime.now()

# Function for calculating backup ages
def findAgeIndex(datetimeObj):
    """Finds the index such that datetimeOjb is older than bounds[index] without being 
    older than bounds[index+1] (unless index corresponds to the end of bounds) """
    for index in range(len(bounds)-1):
        if now - datetimeObj < dt.timedelta(bounds[index+1]):
            return index
    
    return index+1 # Age was not less than any bound, so it is the final index of bounds

# Function for turning backup string into datetime instance
def dateof(backupStr):
	return dt.datetime.strptime(backupStr,dtFormat)


#
# Get list of backups in current directory ordered oldest to newest
#

backuplist = glob.glob(globFormat)
backuplist.sort()

# The first and last backups are never deleted, so if there are no other backups then 
# there are none to delete, so exit script
if len(backuplist) < 3:
    from sys import exit
    exit()

#
# Loop through the backups and delete those that are too close together
#

# Prepare loop variables
# Remove newest backup (never deleted)
backuplist.pop()
# Preserve oldest backup and set as first previous backup reference
prevBackup = backuplist.pop(0)
# Index to track which backup age class the loop is in
ageIndex = findAgeIndex(dateof(prevBackup))
# List to track backups to be deleted
deletions = []

# Loop through backups and identify those to be deleted
for backup in backuplist:
    if now - dateof(backup) > dt.timedelta(bounds[ageIndex]):
        # backup is in the same age class as prevBackup
        if dateof(backup) - dateof(prevBackup) < dt.timedelta(spacings[ageIndex]):
            deletions.append(backup)
        else:
            prevBackup = backup
    else:
        # backup is in a new age class
        ageIndex = findAgeIndex(dateof(backup))
        prevBackup = backup
        
# Delete backups
for backup in deletions:
    shutil.rmtree(backup)