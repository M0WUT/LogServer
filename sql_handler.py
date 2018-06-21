#!/usr/bin/python3

import passwords
import MySQLdb
import sys
import requests
import subprocess
import json


#Uploads any new QSOs for 'callsign' to Clublog
#Assumes MySQL database has same name as callsign
#returns 	0 - Success
#		1 - SQL Error
#		2 - Clublog Error
def clublog_upload(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
		print("\nStarting Clublog upload for {}".format(callsign))

	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1

	c = db.cursor()
	c.execute("SELECT QsoDate, TimeOn, Freq, Band, Mode, `Call`, RstSent, RstRcvd FROM log WHERE ClublogQsoUploadStatus = 'N' ORDER BY QsoDate, TimeOn")
	qsos = c.fetchall()
	if(qsos == ()):
		print("Nothing to upload to Clublog")
		return 0

	logfile = open ("/tmp/log.adi", "w")
	logfile.write("<EOH>\r\n")
	for qso in qsos:
		#Frequency is specified in kHz.000, ADIF needs MHz with digits below kHz ignored
		freq = qso[2]
		freq = freq.split('.')[0] #Seperate off only the whole number of kHz(the bit before the decimal point)
		freq = freq[:-3] + '.' + freq[-3:]
		logfile.write("<QSO_DATE:8>{} <TIME_ON:6>{} <FREQ:{}>{} <BAND:{}>{} <MODE:{}>{} <CALL:{}>{} <RST_SENT:{}>{} <RST_RCVD:{}>{} <EOR>\r\n".format(qso[0], qso[1], len(freq), freq, len(qso[3]), qso[3], len(qso[4]), qso[4], len(qso[5]), qso[5], len(qso[6]), qso[6], len(qso[7]), qso[7]))
	logfile.close()

	#Now have ADIF file ready for upload to Clublog
	url = "https://clublog.org/putlogs.php"
	files = {'file' : open("/tmp/log.adi", "rb")}
	values = {'email' : passwords.CLUBLOG_EMAIL, 'password' : passwords.CLUBLOG_APPLICATION_PASSWORD, 'callsign' : callsign, 'api' : passwords.CLUBLOG_API_KEY}
	errorCode = requests.post(url, files=files, data=values).status_code
	if(errorCode == 200):
		print("Uploaded {} QSOs to Clublog".format(callsign))
		c.execute("UPDATE log SET ClublogQsoUploadStatus = 'Y' WHERE ClublogQsoUploadStatus = 'N'")
		db.commit()
		return 0
	else:
		print("Clublog Upload for {} failed".format(callsign))
		return 2




#Uploads any new QSOs for 'callsign' to LoTW
#Expects MySQL database to have same name as callsign

#returns	0: Success - Either nothing to do or all fine
#		1: Cancelled by User
#		2: Rejected by LoTW
#		3: Unexpected response from TQSL server
#		4: TQSL error
#		5: TQSLlib error
#		6: Unable to open input file
#		7: Unable to open output file
#		8: All QSOs were duplicates or out of range
#		9: Some QSOs were duplicates or out of range
#		10: Command Syntax Error
#		11: LoTW Connection Error
#		12: Error connectiong to SQL database
#		13: My callsign gives invalid DXCC from Clublog 
def lotw_upload(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
		print("\nStarting LoTW upload for {}".format(callsign))

	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 12

	c = db.cursor()
	#Deal with LotW first, each locator I used must be uploaded seperately
	c.execute("SELECT DISTINCT MyGridSquare FROM log WHERE LotwQslSent = 'N'")
	locators = c.fetchall() # Locators now contains all the locators with un-uploaded QSOs
	if(locators == ()):
		print("Nothing to upload to LoTW")
		return 0

	for locator in locators: #For each locator
		print("Uploading callsign from {} in locator {}".format(callsign, locator[0]))
		#Get all of the QSOs that haven't been uploaded yet
		c.execute("SELECT QsoDate, TimeOn, Freq, Band, Mode, `Call`, RstSent, RstRcvd FROM log WHERE LotwQslSent = 'N' AND MyGridSquare = %s ORDER BY QsoDate, TimeOn", (locator[0],))
		qsos = c.fetchall()
		logfile = open ("/tmp/log.adi", "w")
		logfile.write("<EOH>\r\n")
		for qso in qsos:
			#Frequency is specified in kHz.000, ADIF needs MHz with digits below kHz ignored
			freq = qso[2]
			freq = freq.split('.')[0] #Seperate off only the whole number of kHz(the bit before the decimal point)
			freq = freq[:-3] + '.' + freq[-3:]
			logfile.write("<QSO_DATE:8>{} <TIME_ON:6>{} <FREQ:{}>{} <BAND:{}>{} <MODE:{}>{} <CALL:{}>{} <RST_SENT:{}>{} <RST_RCVD:{}>{} <EOR>\r\n".format(qso[0], qso[1], len(freq), freq, len(qso[3]), qso[3], len(qso[4]), qso[4], len(qso[5]), qso[5], len(qso[6]), qso[6], len(qso[7]), qso[7]))
		logfile.close()
		#logfile now contains an ADIF with the new QSOs to be uploaded, now need to overwrite LotW Locator File so this log gets uploaded with correct locator
		#Start by requesting my DXCC from Clublog
		url = 'https://clublog.org/dxcc'
		payload = {'call' : callsign, 'api' : passwords.CLUBLOG_API_KEY}
		myDxcc = requests.get(url, payload).text
		if(myDxcc == 0):
			print("My Callsign gives invalid DXCC from Clublog")
			return 13

		#Write station information to LoTW config file
		locatorFile = open("/home/pi/.tqsl/station_data", "w")
		locatorFile.write("<StationDataFile>\n")
		locatorFile.write("  <StationData name=\"test\">\n")
		locatorFile.write("    <CALL>{}</CALL>\n".format(callsign))
		locatorFile.write("    <CQZ>0</CQZ>\n")
		locatorFile.write("    <DXCC>{}</DXCC>\n".format(myDxcc))
		locatorFile.write("    <GRIDSQUARE>{}</GRIDSQUARE>\n".format(locator[0]))
		locatorFile.write("    <ITUZ>0</ITUZ>\n")
		locatorFile.write("  </StationData>\n")
		locatorFile.write("</StationDataFile>\n")
		locatorFile.close()

		#Upload the ADIF to LoTW
		lotwResult = subprocess.call(["tqsl", "-a", "abort", "-d", "-l", "test", "-u", "-x", "/tmp/log.adi"]) #, stderr = subprocess.DEVNULL)

		#Check error code
		if(lotwResult == 0):
			c.execute("UPDATE log SET LotwQslSent = 'Y' WHERE MyGridSquare = %s AND LotwQslSent = 'N'", (locator[0],)) #All fine, update log
			db.commit()
		elif(lotwResult == 1): print("Cancelled by user")
		elif(lotwResult == 2): print("Rejected by LoTW")
		elif(lotwResult == 3): print("Unexpected Response from TQSL Server")
		elif(lotwResult == 4): print("TQSL Error")
		elif(lotwResult == 5): print("TQSLlib Error")
		elif(lotwResult == 6): print("Unable to open input file")
		elif(lotwResult == 7): print("Unable to open output file")
		elif(lotwResult == 8): print("All QSOs were duplicates or out of range")
		elif(lotwResult == 9): print("Some QSOs were duplicates or out of range")
		elif(lotwResult == 10): print("Command Syntax Error")
		elif(lotwResult == 11): print("LoTW Connection Error")
		else: print("Unknown TQSL Error")

		db.close()
		return lotwResult

#If any fields have blank DXCC entries, ask Clublog and update them
#returns	0: success - either nothing to do or all done fine
#		1: Error connecting to SQL database
#		2: One or more callsign returned error from Clublog

def log_tidy(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
		print("\nBegun tidying for {}".format(callsign))

	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1

	c = db.cursor()
	c.execute("SELECT `Call` FROM log WHERE Dxcc = ''")
	callsigns = c.fetchall()
	if(callsigns == ()):
		print("No tidying required")
		db.close()
		return 0

	else:
		errorCode = 0
		for call in callsigns: #I know the helpage says don't iterate but there shouldn't be many
			url = 'https://clublog.org/dxcc'
			payload = {'call' : call[0], 'api' : passwords.CLUBLOG_API_KEY, 'full' : '1'}
			dxcc = requests.get(url, payload).text
			info = json.loads(dxcc)
			if(info['DXCC'] == 0):
				print("No DXCC found for {}".format(call[0]))
				errorCode = 2
			else:
				print("Updating {} to Country: {}".format(call[0], info['Name']))
				c.execute("UPDATE log SET Dxcc = %s, Country = %s WHERE `Call` = %s", (info['DXCC'], info['Name'].title(), call))
		db.commit()
		db.close()
		return errorCode


if __name__ == '__main__':
	clublog_upload("M0WUT")

