# Backup notes

## Introduction

`wsbackup.py` is a script for running simple, versioned backups with `rsync` to
either a local or remote machine.

### Use case

The script works best for backing up lightly used data sets, such as the files
on a desktop or laptop computer. For large datasets, especially those
containing large, constantly changing files, a dedicated backup product should
be used instead. Even for personal files, there are several other options that
could considered including backup tools like
[Borg](ihttp://borgbackup.readthedocs.org) (best for the case of constantly
changing large files since it uses chunked deduplication) or file sync tools
that support versioning like [Syncthing](https://syncthing.net/),
[ownCloud](https://owncloud.org/), and
[Seafile](https://www.seafile.com/en/home/). The main advantage of
`wsbackup.py` over these tools is its simplicity. It is just a wrapper around
`rsync` and just creates new folder on the file system for each backup (with
unchanged files hardlinked to save space).

## Installation

The only requirements for the script are `python` (version 3.4 or higher),
`rsync`, and the Python package `PyYaml` (used for parsing the config file).

## Usage

Here is the output of `wsbackup.py -h`:

```
usage: Backup files via rsync [-h] --config CONFIG [--rsync-opt RSYNC_OPT]

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to yaml configuration file defining backup
                        procedure.
  --rsync-opt RSYNC_OPT, -r RSYNC_OPT
                        Arguments passed to rsync (be sure to use -r="--
                        option" syntax to avoid --option being consumed by
                        this command).
```

Most of the available options are set in the config file rather than on the
command line. The config file is written in YAML format.
`wsbackup_config_template.yaml` is a heavily commented example file containing
most of the possible config settings. Please read it to understand the details.

The basic usage is to run `wsbackup.py -c <config.yaml>`. The config file
specifies some number of paths as "sources" and one path as a "destination".
All of the source paths will be copied by `rsync` into a subdirectory of the
destination named after the date of the backup. There is a remote option that
can be set to have `rsync` to connect to either the sources or the destination
via `ssh`. The config file also has entries for keeping logs of which files
were backed up, excluding files, and passing specific options to `rsync`.

## How it works

The basic outline of steps taken by the script is as follows:
* Open the logfile
* Check for a lockfile and exit if one is found indicating a previous back up
  that is still running.
* Test `ssh` connection if using a remote
* Transfer the files using `rsync` to a subfolder of the destination named
  "incomplete" using the `--link-dest` `rsync` option to hardlink unchanged
files to the previous backup (note that an interrupted backup will leave a
partial transfer in this `incmplete` folder and a subsequent backup will
effectively resume the previous one).
* Once the transfer finishes, rename the "incomplete" subfolder with the
  current time.
* Change the "latest" symlink to point to the new backup folder.
* Prune older backups using the aging parameters specified in the config file.
* Transfer the logfile to the destination.
* Remove the lockfile

These notes describe setting up a simple Ubuntu backup server for backing up
remotely from another computer running Linux or OSX.  It is probably also
possible to follow these notes to backup to a computer running OSX or backup
from a computer running Windows (via cygwin) (Some subtle adjustments would
probably be necessary.  For instance, you might need to tell rsync to use less
precision in comparing file modification times).  These notes also assume that
the backup server is being set up on a router, but it would probably not be too
hard to set it up without one.

This is not the first wrapper script written to use `rsync` as a versioned
backup tool. Here a couple that I looked at for inspiration:

* (http://randombytes.org/backups.html)
* (http://www.jan-muennich.de/linux-backups-time-machine-rsyn)

## Appendix

Here are some additional (old) notes on setting up systems to backup using the
script. These notes used to be longer (check the git history) because I wrote
them when I was knew to Linux and did not know what was obvious and what
wasn't. I am keeping them here but cutting them down to the basic steps that
can be used as starting points for looking up more complete guides online.

### Choosing a file system

The script works best when the destination supports hard links (which let
multiple paths on the file system point to the underlying file, saving space).
ext3 and ext4 (usually the default on Linux systems) support hard links. NTFS
also supports hard links but I have never tried to use it. NTFS has the benefit
being better supported across all platforms than ext4, so it might be worth
considering, but do some research on cross-platform issues if they are relevant
to you. Some NTFS features available on Linux might not work when the partition
is mounted under Windows.

### Setting up a Linux backup server

* Install Linux. Ubuntu has a user friendly installer and long term support
  release. Debian also works well though the installer requires a little more
user knowledge.

* Create a user account that you want to use for logging in remotely

* Install the backup disk (if it is not the boot drive...) and assign it a static
  name (desktop environments like Unity or GNOME will mount drives
automatically but might not give it the same name each time).

* Create a directory on the backup disk to hold the backups and make sure that
  the backup user account has write access to the directory (using chmod).

* Install OpenSSH as a server. In some distributions, the server and client are
  separate packages. Some distributions set up the `ssh` server to run at
startup when you install it.

#### Remote acces with `ssh`

There are a lot of bots that crawl the web trying to brute force `ssh` servers
with password guesses. Disable password authentication before opening your
server to the internet so that there is no chance that they compromise your
server (though using a long, strong password should be safe).

* Generate a key file with `ssh-keygen` on the client that will be connecting
  to the server.

* Copy the key into the server's `authorized_keys` file in `~/.ssh`.
  `ssh-copy-id` will do this for you.

* Test that connecting with a key works.

* Disable password authentication on the server (modify `sshd_config` in
  `/etc`) and restart `sshd` (see, eg,
(http://askubuntu.com/questions/229944/how-to-set-up-an-rsync-backup-to-ubuntu-securely)).

* If you are annoyed by the bots trying to log in, consider using `fail2ban`.
  On some Linux distributions, just installing it will set it up to run on
`ssh` failures with reasonable default settings.

* Set up your router (assuming the `ssh` server is behind a router):

  - In the router settings (typically accessed via the web interface at
    192.168.1.1), set port 22 (the default ssh port) to be forwarded to the
server (typically under firewall settings).

	+ How this is set up depends on the router, but try to do it in a way that
	  will persist across reboots (e.g. use the server's hostname or MAC
address).

	+ This allows you to `ssh` into the server from the outside if you know the
	  router's ip address.

	+ You can check the router's ip address by going to a site like
	  (whatismyip.org) from a machine connected to the router.

  - Setting up dynamic DNS is more robust than using the router's ip address.

	+ Many routers support some DNS services natively (look for DNS settings in
	  the various settings sections).

	+ One DNS service with a free option is (www.no-ip.com).

#### Encryption / security

* Using `ssh` encrypts data in transit to the server. If you only allow access
  via a public/private key pair, the data should be pretty safe, especially if
you use `fail2ban` and do not install a lot of extra applications on the server
(and install security updates in a timely manner and check authentication
logs).

* If you are worried about the data on the server's hard drive, encryption the
  partition or container using LUKS.

* If you are worried about the data being accessible if the server is
  compromised, you could consider using `encfs --reverse` to mount the folder
as an encrypted file system and backing that up instead. Be aware that `encfs`
has been audited and found to contain some security flaws that still remain
after a couple. I'm not aware of any other program (other than very small
projects that I wouldn't trust with important data) that have a feature similar
to `encfs --reverse`. One alternative for encryption is `git annex` though it
is not simple to set up (and would be used instead of this script). `borg` also
has encryption features.

* If you do use encryption, be sure to make several robust backups of your
  encryption keys.

* Consider the likelihood of your server being compromised versus your machine
  being backed. It might be more secure to run the script from your server with
your machine to be backed up as a remote source, so that your machine does not
need to have full access to the server.

* Some other measures to consider:

	+ Use a firewall on the server (ufw)
	+ Use a non-standard port for the transfer
	+ Use port-knocking

	+ Some of these suggestions are discussed in the references below:

		- <http://askubuntu.com/questions/85462/what-is-my-computer-ip-address-knowing-that-i-have-a-router>
		- <http://www.cyberciti.biz/faq/unix-linux-bsd-osx-change-rsync-port-number/>
		- <http://www.howtogeek.com/115116/how-to-configure-ubuntus-built-in-firewall/>
		- <http://hints.macworld.com/article.php?story=20031024013757927>
		- <http://www.fail2ban.org/wiki/index.php/Main_Page>
