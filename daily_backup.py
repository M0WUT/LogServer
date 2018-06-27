import passwords
import callsigns
import subprocess
import time


def handle():
	callsignString = ""

	for callsign in callsigns.callsign_list():
		callsignString += callsign.replace('/', '_') + ' '


	callsignString = callsignString.rstrip() #Remove trailing space
	print("Backing up databases for: " + callsignString)


	cmd = "mysqldump -u {} -p{} -h {} -P {} --databases {}".format(passwords.SQL_USERNAME, passwords.SQL_PASSWORD, passwords.SQL_SERVER, passwords.SQL_PORT, callsignString)
	args = cmd.split(' ')

	saveFileName = "{}.gz".format(time.strftime('%d-%m-%Y', time.gmtime()))
	saveFile = open(saveFileName, 'w')

	dumpProcess = subprocess.Popen(args, stdout= subprocess.PIPE)
	saveProcess = subprocess.Popen(["gzip"], stdin=dumpProcess.stdout, stdout=saveFile)
	saveProcess.wait()
	saveFile.close()
	uploadProcess = subprocess.Popen(["/home/pi/Dropbox-Uploader/dropbox_uploader.sh", "upload", saveFileName, saveFileName])
	uploadProcess.wait()
	deleteTempFile = subprocess.Popen(["rm", saveFileName])
	deleteTempFile.wait()
	print("Done")
if(__name__ == '__main__'):
	handle()
