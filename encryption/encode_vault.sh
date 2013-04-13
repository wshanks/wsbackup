#!/bin/bash

# This script mounts an encrypted directory with encfs, mirrors it with another 
# unencrypted directory, and then unmounts it.

# This script assumes that you have three directories inside of the same parent: plain,
# enc, and tmp.  plain (can be named anything) should have all the files to be encrypted
# and this script.  enc (name can be set below) will hold the encrypted versions of the
# files.  tmp (name can be set below) is a temporary mount point.  The .xml file with
# the encryption key should be in the parent directory of plain, enc, and tmp (specify
# the name below in the XML variable, or specify a path relative to that directory).

# It is possible to pass in a password with the -p flag.  This option is useful for 
# calling this script from another script, but don't use it in a setting where the input
# is logged since then the password will be viewable.

# User settings
# .encfs6.xml file name
XML=".encfs6.xml"
# Path to encfs (AppleScript doesn't search outside /usr/bin).
ENCFS="/usr/local/bin/encfs"
# Temporary mount directory
TMP="tmp"
# Encrypted directory
ENC="enc"

while getopts ":p:" OPTIONS; do
  case $OPTIONS in
    p ) PASS=$OPTARG;;
    \?)
        echo "Usage: $0 [-p password]"
        exit 1
    ;;
  esac
done

# DIR is directory containing this script
DIR="$( cd -P "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# PARENT is the parent directory of DIR
PARENT="$( cd -P "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"

if [ $PASS ]
then 
	echo $PASS | ENCFS6_CONFIG="${PARENT}/${XML}" \
		"${ENCFS}" -S "${PARENT}/${ENC}/" "${PARENT}/${TMP}/" -o volname="tmp"
else
	ENCFS6_CONFIG="${PARENT}/${XML}" \
		"${ENCFS}" "${PARENT}/${ENC}/" "${PARENT}/${TMP}/" -- -o volname="tmp"
fi

for I in 1 2 3 4 5 6 7 8 9 10
do
	# Make sure that the drive mounted before copying files in
	if ! mount | grep encfs | grep "${PARENT}/${TMP}" >/dev/null;
	then
		# Not mounted yet
		:
	else
		# On OSX use umount; on Linux use fusermount -u
		rsync -av --delete "${DIR}/" "${PARENT}/${TMP}" && umount "${PARENT}/${TMP}"
		break
	fi
	sleep 2
done