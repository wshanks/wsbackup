# This script prompts for a password and then calls encode_vault.sh
# with that password.  It should be stored in the same directory as
# encode_vault.sh

tell application "Finder" to get folder of (path to me) as alias
set parentDir to POSIX path of result

set pword_dialog to display dialog Â
	"Vault password:" default answer "" with hidden answer
set pword to the text returned of pword_dialog

do shell script (parentDir & "encode_vault.sh -p " & pword)