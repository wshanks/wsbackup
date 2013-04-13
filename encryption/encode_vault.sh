#!/bin/bash

# This script mounts an encrypted directory with encfs, mirrors it with another 
# unencrypted directory, and then unmounts it.

# This script assumes that you have three directories inside of the same parent: plain,
# enc, and tmp.  plain should have all the files to be encrypted.  enc will hold the
# encrypted versions of the files.  tmp is a temporary mount point.  This script should be
# saved in the plain directory, as should the .xml file with the encryption key (specify
# the name below in the XML variable).

# It is possible to pass in a password with the -p flag.  This option is useful for 
# calling this script from another script, but don't use it in a setting where the input
# is logged since then the password will be viewable.

# .encfs6.xml file name (does not have to be .encfs6.xml)
XML=".encfs6.xml"
ENCFS="/usr/local/bin/encfs"

while getopts ":p:" OPTIONS; do
  case $OPTIONS in
    p ) PASS=$OPTARG;;
    \?)
        echo "Usage: $0 [-p password]"
        exit 1
    ;;
  esac
done

# Dir is directory containing this script
DIR="$( cd -P "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"

if [ $PASS ]
then 
	echo $PASS | ENCFS6_CONFIG="${DIR}/plain/${XML}" \
		"${ENCFS}" -S "${DIR}/enc/" "${DIR}/tmp/" -o volname="tmp"
else
	ENCFS6_CONFIG="${DIR}/plain/${XML}" \
		"${ENCFS}" "${DIR}/enc/" "${DIR}/tmp/" -- -o volname="tmp"
fi

for I in 1 2 3 4 5 6 7 8 9 10
do
	# Make sure that the drive mounted before copying files in
	if ! mount | grep encfs | grep "${DIR}/tmp" >/dev/null;
	then
		# Not mounted yet
	else
		# On OSX use umount; on Linux use fusermount -u
		rsync -av --delete "${DIR}/plain/" "${DIR}/tmp" && umount "${DIR}/tmp"
		break
	fi
	sleep 2
done