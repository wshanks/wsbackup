#!/bin/bash
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
#     Files: wsbackup_transfer.sh and wsbackup_prune.py
#   Created: 4 February 2012
#   Current: 31 December 2012
#
#   Purpose: Backup source to target and run pruning script to retain progressively less
#            frequent backups
#
#
# --------------------------------------
#
# History:
#
# 31 December 2012: - Replace backup rotation code with python pruneScript
#                   - Remove identifier subdirectory
#                   - Change source directory setup to allow transfer of subset of 
#                     directories below a base path
#                   - Make exclude file optional
#                   - Use single "incomplete" folder so that interrupted transfers are 
#                     resumed
#
# 8 March 2012   : - fixed check for lockfile
#
# 3 March 2012   : - added excludes
#		           - made it possible to change the ‘hostname’ identifier
#                  - lockfile is placed locally and is used to check the PID of the backup
#                  - should a lockfiles exists, but there is no process running with it’s 
#                    PID, backup starts again and remaining incomplete folders are removed
#                  - should work with folders with spaces (every source and target is 
#                    enclosed in quotes)
#                  - start, finish and errors are written to a log file, every line 
#                    includes the PID
#
# 4 February 2012: - first version
#
# --------------------------------------

# exit codes are taken from /usr/include/sysexits.h

#############################
# User adjustable settings
#############################

# Paths to files to be backed up
# Path to root directory of folders to be backed up (must end in '/')
backuppath='/path/to/back up/root/'
# files/directories on backuppath to back up
backupitems=('backup 1' 'backup 2' 'backup 3')
backupitempaths=("${backupitems[@]/#/$backuppath}")
#
# Settings for server to back up to
# target must end in /
target='/path/to/remote/backup/'
ssh_user='user'
ssh_server='remote.server.org'
#
# Other componenet names
# the identifier is used to name a lock- and logfile (stored in the same directory as 
# this script)
# identifier is also used to look for an excludes file (with a .xcl extension) in the 
# same directory as this script
identifier='backupid'
# Name of python script to clean up backups
# The python script should be in the same folder as this transfer script.  It is 
# transferred to the server and run from the target directory
pruneScript='wsbackup_prune.py'
# Format used for naming backup directories
dateFormat='+%Y-%m-%d_%Hh%Mm%Ss'

#############################
# Start script
#############################

# Date for this backup.
dateStr=`date ${dateFormat}`

# Process ID for this backup
mypid=${$}

# excludes file should be in the same directory as backup script with filename of 
# identifier and xcl extension
DIR="$( cd -P "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
excludes="${DIR}/${identifier}.xcl"
# If exclude file does not exist, create an empty one.
if [ ! -f "${excludes}" ]
then
	touch "${excludes}"
fi

# Every step is logged to a logfile
logfile="${DIR}/${identifier}.log"

echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] -- backup started" >> "${logfile}"

# Check and create lockfile, the identifier is used as a name for the lockfile
lockfile="${DIR}/${identifier}.lck"

if [ -f "${lockfile}" ]
then
  # Lockfile already exists, check if it belongs to a running process
  read -r lockpid < "${lockfile}" #Read the first line which contains a PID
  if [ -z "`ps -p ${lockpid} | grep ${lockpid}`" ]
  then
    # The process doesn't exist anymore. Should there be an incomple folder, it will be removed at the end of the script.
    echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] Lockfile for ghost process (PID: ${lockpid}) found, continuing backup." >> "${logfile}"
  else
    echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] Lockfile '${lockfile}' for running process (PID: ${lockpid}) found, backup stopped." >> "${logfile}"
    exit 73 # can't create (user) output file
  fi
fi

# The lockfile doesn't exist or belongs to a ghost process, make or update it containing the current PID.
echo ${mypid} > "${lockfile}"

# Create the connection string.
ssh_connect="${ssh_user}@${ssh_server}"

# Check if the ssh connection can be made, a ssh keypair without keyphrase must exist.
ssh -q -q -o 'BatchMode=yes' -o 'ConnectTimeout 10' ${ssh_connect} exit &> /dev/null

if [ $? != 0 ]
then
  echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] SSH connection ${ssh_connect} failed." >> "${logfile}"

  # Remove lockfile
  rm -f "${lockfile}"

  exit 69 # service unavailable
fi

# check if target exists
if ssh ${ssh_connect} "[ ! -d '${target}' ]"
then
  echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] Target '${target}' does not exist, backup stopped." >> "${logfile}"

  # Remove lockfile
  rm -f "${lockfile}"

  exit 66 # cannot open input
fi

# -- make backup
# Make the actual backup, note: the first time this is run, the latest folder
# can't be found. rsync will display this but will proceed.
# --xattrs \ # Option not available in rsync that comes with OSX
# --chmod=ug+w Necessary for old backups to be deletable
rsync \
--archive \
--compress \
--human-readable \
--delete \
--chmod=ug+w \
--link-dest="${target}latest" \
--exclude-from "${excludes}" \
"${backupitempaths[@]}" \
"${ssh_connect}:${target}incomplete"


# Backup complete, it will be moved to the properly named folder.
ssh ${ssh_connect} "mv '${target}incomplete' '${target}${dateStr}'"
# Create a symlink to new backup .
ssh ${ssh_connect} "rm -f '${target}latest' && ln -s '${target}${dateStr}' '${target}latest'"

# Check for prune file and transfer if missing
rsync --compress "${DIR}/${pruneScript}" "${ssh_connect}:${target}"

# Delete old backups
ssh ${ssh_connect} "cd '${target}' && python '${pruneScript}'"

echo `date '+%Y/%m/%d %H:%M:%S '` "[${mypid}] -- backup finished" >> "${logfile}"

# Remove lockfile, this must always be done at the latest moment possible to avoid conflicting processes.
rm -f "${lockfile}"
