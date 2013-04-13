Backup notes
============
Introduction
------------
These notes describe setting up a simple Ubuntu backup server for backing up remotely from another computer running Linux or OSX.  It is probably also possible to follow these notes to backup to a computer running OSX or backup from a computer running Windows (via cygwin) (Some subtle adjustments would probably be necessary.  For instance, you might need to tell rsync to use less precision in comparing file modification times).  These notes also assume that the backup server is being set up on a router, but it would probably not be too hard to set it up without one.

Choose back up disk file system
-------------------------------
I think the best choice is just to go with ext3 since it is native to Linux.  The downside is that it does not have as good cross-platform support as other systems such as FAT32 (FAT32 does not have the Unix permissions that rsync tries to copy with the -a flag.  Also, FAT32 does not support symlinks and has reduced time resolution compared to other options), so it might be difficult to get a lot of files off the backup disk quickly (i.e. you couldn't plug the disk into a computer running OSX or Windows without installing a utility to translate from ext3).  Here are some resources as of 1/1/2013 for accessing ext3:

Windows
<http://www.ext2fsd.com/>

OSX
<http://reviews.cnet.com/8301-13727_7-57457850-263/how-to-manage-ext2-ext3-disks-in-os-x/>
<http://osxfuse.github.com/>
<http://sourceforge.net/projects/fuse-ext2/>

Set up Ubuntu
----------------------------------------
There are few steps here:

* Install Ubuntu (<http://www.ubuntu.com/download/desktop>). It should be pretty straightforward to set up a USB installer following Ubuntu's directions.  To be safe, choose a strong password for any user accounts that can sudo.

* Create a user account that you want to use for logging in remotely (this could be the same as the account that you created when installing Ubuntu, just be aware of its login name and password).

* Install the backup disk (if it is not the boot drive...).  Assign a static name to the drive (i.e. don't just use the default name that Ubuntu gives it so it can't be unmounted/remounted and assigned a different name).

* Create a directory on the backup disk to hold the backups and make sure that the backup user account has write access to the directory (using chmod).

* Install an ssh server.  To do this, just run this command: 

`sudo apt-get install openssh-server openssh-client`

By default, the server is set to run on startup.  So there is not much more to do, but see the section on remote access below.

Set up RSA key pair with ssh-keygen and ssh-copy-id
---------------------------------------------------
Allowing traditional login via a password is not that safe because an attacker could try to crack it via repeated logins.  An alternative is to setup an RSA keypair between the remote computer to be backed up and the server.  This is basically like using a really long password that is stored on the two computers, so no password needs to be entered each time a connection is made.

I was setting up a laptop running OSX as my remote machine, so I did the following: 

* ran ssh-keygen on the remote machine in the home directory.  

* installed ssh-copy-id with:

`sudo /usr/bin/curl "http://hg.mindrot.org/openssh/raw-file/c746d1a70cfa/contrib/ssh-copy-id" -o /usr/bin/ssh-copy-id`

(I had to use `/usr/bin/curl` because another piece of software messed up my path to curl).

* ran `ssh-copy-id user@server` to copy the RSA key to the server.  Here  `user` is the login name to use on the server and `server` is the ip address of the server.  We haven't set up remote access yet, so the remote machine needs to be connected to the same router as the server and the ip address is the local ip address on the router (probably 192.168.1.x for some number x -- on most routers, you can check the ip address by logging into at with a web browser at 192.168.1.1).  You should be prompted to enter the user account's password.

Set up remote access
--------------------
Now we are almost ready to open up the server to the outside world.  

Before exposing the server to the outside, we review a few notes about security.  Security concerns are addressed here (I posted the question):

<http://askubuntu.com/questions/229944/how-to-set-up-an-rsync-backup-to-ubuntu-securely>

Basically, set `PasswordAuthentication no` in `/etc/sshd_config` and make sure that `challengeresponse` is also set to `no`.  If you don't have a router, you should turn on a firewall and consider fail2ban.

To open the server to the outside world, set up the router to forward TCP on port 22 (the default port for ssh) to the server.  On my Actiontec router from Verizon, this was simple to do (login into the router at 192.168.1.1, go to "Firewall Settings"->"Port forwarding", and then select the server in the first drop-down menu and SSH in the second).  On other routers, it might be necessary to enter the server's MAC address and assign it a static ip address on the router and then forward the port to that static address.

Now the server can be accessed via ssh from the outside world.  To do so, you need the ip address of the router.  The ip address can be checked in various ways, for example by going to <http://whatismyip.org/>.  Most home internet connections have dynamic ip addresses that can change.  To create a static address that will always work, you can use a dynamic DNS service like <http://www.no-ip.com/> (a good free one).  The Actiontec router is set up to work with several dynamic DNS services (including no-ip; just go to "Advanced"->"Dynamic DNS" in the router web interface), so I just set it up to update no-ip when its ip address changes.  Alternatively, one could set up a client like ddclient (<http://sourceforge.net/apps/trac/ddclient/>) on the server to monitor the ip address and update the dynamic DNS service.

A lot of the dynamic DNS services have cut back on their free options, so it might be necessary to hunt around for one (<http://freedns.afraid.org> is another one that looked promising but wasn't a default option in my router).  I had set up a script to check my ip address and upload it to an ftp server before the respondent to my askubuntu.com question said to just go with the simplest solution.  Something like that is an option though.  All you need is something that will check the ip address (by going to e.g. <checkip.dyndns.org> and parsing the content) and then send something out somewhere when a change is noticed.  So far, I have left my router on and plugged in and the ip address has not changed in over a month, so you could get away without setting up anything as long as you were okay with the occasional break in connectivity (dependent upon how often your ip address changes).

Backup script setup
-------------------
Finally, a script needs to be written to handle the transferring and managing of backups from the remote machine to the server.  I used the following two scripts as my starting point:

<http://randombytes.org/backups.html>
<http://www.jan-muennich.de/linux-backups-time-machine-rsyn>

The rsync command does most of the work.  The rest of the scripts are basically just error checking the connection and previously started backups and then deleting old backups.  You can set the script to run automatically with something like cron or Automator or you can just run it by hand.  I like creating single line AppleScript applications that call other scripts with "do shell script" so that I can run them from SpotLight.

My current scripts are `wsbackup_transfer.sh` and `wsbackup_prune.py` available at <https://github.com/willsALMANJ/wsbackup>.

The generic entries in my excludes file are:
.DS_Store
Thumbs.db
*~
._*

Encrypt data (optional)
-----------------------
If you're just backing up data to a private server, it's probably not necessary to encrypt it beforehand.  The transfer scripts described above will encrypt the data as it is transferred via ssh, and if the server is only accessible via an RSA key it should be pretty secure.  However, if the server is set up to share the files more publicly or the data is backed up to third party cloud storage service (e.g. DropBox), you might want to encrypt some file before transferring, just to protect it (e.g. in case someone gets your DropBox password).  

One encryption option is encfs which works on Linux or OS X (see [this custom homebrew formula](https://github.com/jollyjinx/encfs.macosx) for one option for getting encfs working with OS X).  It allows you to mount a folder ("tmp") as a drive linked to a second folder ("enc").  Anything that is saved into tmp is actually saved into "enc" in encrypted form.  This functionality does not totally encrypt the data (each file is encrypted separately so you can still read the file size and see the directory hierarchy), but it does work with versioned backups.

In the `encryption` folder, there are two scripts, `encode_vault.sh` and `vault_update.applescript`, that help with encrypting files for back up.  `encode_vault.sh` mounts an encfs folder named `enc` to a folder named `tmp`, syncs the contents of the folder containing `encode_vault.sh` into `tmp` and then unmounts it.  The folder containing `encode_vault.sh` should be named `plain` and should also contain the encfs .xml file for the encrypted folder.  The `vault_update.applescript` script just calls `encode_vault.sh` after prompting for the password.  It could be saved as an .app file for easy calling from Spotlight in OS X.  Note that the script is set up to be run in OS X, and the `umount` command needs to be changed to `fusermount -u` for Linux.

When you set up the encrypted folder for the first time, encfs creates a file named `.encfs6.xml` in the encrypted folder.  This file contains the password encrypted version of the encryption key for the encfs folder.  The script needs this file to be moved to the `plain` folder because the idea is that the `enc` folder will be backed up to a less secure location.  If the `.encfs6.xml` file were left in the `enc` folder, someone would just need to guess the password to unencrypt the key and thus all of the files.  Without the `.encfs6.xml` file, someone would need to guess the entire key.  It's probably a good idea to back up the `.encfs6.xml` since the files can't be unencrypted without it, but I'd recommend backing it up somewhere else that it's unlikely that someone trying to access your files would look.  It's not a very big file, so you could, for example, give it an innocuous name and email it to yourself as an attachment.

Appendix: extra stuff not done
==============================

IP update through ftp instead of dynamic DNS
--------------------------------------------
There are some free services available for reserving and updating a dynamic DNS address to point to your home ip.  When I looked into this, most sites recommended DynDNS (of dyn.com) as the premier option that many manufacturers built in support for (stuff like webcams and media streaming devices).  However, Dyn had just decided to discontinue its free service except for allowing one free address that you could get by signing up for their pay service and then canceling during the 14-day free trial.  The free address came with a 30-day inactivity expiration.  There are other sites like no-ip.com and freedns.afraid.org that still have more generally free services, but it seems like in general free dynamic DNS services are being phased out by (pretty cheap) pay services.

An alternative that I thought of was to use an ftp account I have access to to push a file containing the server's ip address to and then to grab that file with the remote computer before connecting with rsync/ssh.  Here are the commands for scripting these sets of actions.  I included an encryption of the ip address just to draw less attention since the ftp transfer was not secure.

Get the current ip address and write to file:
`curl -s checkip.dyndns.org|sed -e 's/.*Current IP Address: //' -e 's/<.*$//' > ip`

Encrypt file with ip address:
`openssl aes-256-cbc -salt -a -e -pass pass:password -in ip -out ipenc`

Push file to ftp account:
`/usr/bin/curl -Q '-SITE CHMOD 600 ip' -u user:password -T ip ftp://ftp.domain.com`

Get file from ftp account:
`/usr/bin/curl -d user:password -T ip ftp://ftp.domain.com`

Decrypt file:
`openssl aes-256-cbc -salt -a -d -pass pass:password -in ipenc -out ip`

Other safety measures
---------------------
These safety measures were discussed at some places but are for more public servers:

* Use a firewall on the server (ufw)
* Use a non-standard port for the transfer
* Use fail2ban

Some of these suggestions are discussed in the references below:

<http://askubuntu.com/questions/85462/what-is-my-computer-ip-address-knowing-that-i-have-a-router>
<http://www.cyberciti.biz/faq/unix-linux-bsd-osx-change-rsync-port-number/>
<http://www.howtogeek.com/115116/how-to-configure-ubuntus-built-in-firewall/>
<http://hints.macworld.com/article.php?story=20031024013757927>
<http://www.fail2ban.org/wiki/index.php/Main_Page>