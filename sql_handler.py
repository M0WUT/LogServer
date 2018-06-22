#!/usr/bin/python3

import passwords
import MySQLdb
import sys
import requests
import subprocess
import json
import location
import re #Regular expression library
import time

#Downloads any new QSLs from LoTW and updates log, sets ClublogQsoUploadStatus back to 'N' for any records changed
#return		0 - Success
#		1 - SQL Error
#		2 - LoTW Download Error
def lotw_download(callsign):
	#Get last time we synced with LoTW to make more efficient
	try:
		file = open("synctime.txt", "r")
		lastLotwSync = file.readline()
	except:
		lastLotwSync = "1945-01-01 00:00:00"
	file.close()

	url = "https://lotw.arrl.org/lotwuser/lotwreport.adi"
	values = {'login' : passwords.LOTW_USERNAME, 'password' : passwords.LOTW_PASSWORD, 'qso_query' : '1', 'qso_qsl' : 'yes', 'qso_qslsince' : lastLotwSync, 'qso_owncall' : callsign}

	result = requests.get(url,values)
	log = result.text
	if(result.status_code != 200):
		print("Error downloading data from LoTW")
		return 2

	#Convert LoTW record to dictionary
	#Code for ADIF parsing from OK4BX: (http://web.bxhome.org/blog/ok4bx/2012/05/adif-parser-python)
	raw = re.split('<eoh>|<eor>(?i)', log) #Split on <eoh> or <eor>, case insensitive
	raw.pop(0) #Remove header
	raw.pop() #Remove End of File junk
	logbook = []
	for record in raw:
		qso = {}
		tags = re.findall('<(.*?):(\d+).*?>([^<\r\n]+)',record)
		for tag in tags:
			qso[tag[0].lower()] = tag[2].upper()
		logbook.append(qso)

	#Update MySQL database
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1

	c = db.cursor()
	errors = 0
	for qso in logbook:
		try:
			c.execute("UPDATE log SET LotwQslRcvd = 'Y' WHERE `Call` = %s AND Band = %s AND Mode = %s AND QsoDate = %s AND TimeOn = %s", (qso['call'], qso['band'], qso['mode'], qso['qso_date'], qso['time_on']))
		except KeyError:
			print("No callsign found in record:")
			print(qso)
			errors += 1

		if(c.rowcount != 1):
			errors += 1
			print("No record found in log for {} at {} on {}, {} {}".format(qso['call'], qso['time_on'], qso['qso_date'], qso['band'], qso['mode']))
	print("{} QSLs for {}  downloaded from LoTW since {}, {} records updated in log".format(len(logbook), callsign, lastLotwSync, len(logbook) - errors))
	db.commit()

	#Save sync time to file
	syncTime = time.strftime('%Y-%m-%d %H:%M', time.gmtime())
	file = open("synctime.txt", "w")
	file.write(syncTime)
	file.close()
	return 0


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
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1

	c = db.cursor()
	c.execute("SELECT QsoDate, TimeOn, Freq, Band, Mode, `Call`, RstSent, RstRcvd, LotwQslRcvd FROM log WHERE ClublogQsoUploadStatus = 'N' ORDER BY QsoDate, TimeOn")
	qsos = c.fetchall()
	if(qsos == ()):
		print("Nothing to upload to Clublog for {}".format(callsign))
		return 0

	logfile = open ("/tmp/log.adi", "w")
	logfile.write("<EOH>\r\n")
	for qso in qsos:
		#Frequency is specified in kHz.000, ADIF needs MHz with digits below kHz ignored
		freq = qso[2]
		freq = freq.split('.')[0] #Seperate off only the whole number of kHz(the bit before the decimal point)
		freq = freq[:-3] + '.' + freq[-3:]
		logfile.write("<QSO_DATE:8>{} <TIME_ON:6>{} <FREQ:{}>{} <BAND:{}>{} <MODE:{}>{} <CALL:{}>{} <RST_SENT:{}>{} <RST_RCVD:{}>{} <LOTW_QSL_RCVD:1>{} <EOR>\r\n".format(qso[0], qso[1], len(freq), freq, len(qso[3]), qso[3], len(qso[4]), qso[4], len(qso[5]), qso[5], len(qso[6]), qso[6], len(qso[7]), qso[7], qso[8]))
	logfile.close()

	#Now have ADIF file ready for upload to Clublog
	url = "https://clublog.org/putlogs.php"
	files = {'file' : open("/tmp/log.adi", "rb")}
	values = {'email' : passwords.CLUBLOG_EMAIL, 'password' : passwords.CLUBLOG_APPLICATION_PASSWORD, 'callsign' : callsign, 'api' : passwords.CLUBLOG_API_KEY}
	errorCode = requests.post(url, files=files, data=values).status_code
	if(errorCode == 200):
		print("Uploaded QSOs for {} to Clublog".format(callsign))
		c.execute("UPDATE log SET ClublogQsoUploadStatus = 'Y' WHERE ClublogQsoUploadStatus = 'N'")
		db.commit()
		print("QSOs for {} successfully uploaded to Clublog".format(callsign))
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
#		14: No LoTW certificate for the callsign
def lotw_upload(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 12

	c = db.cursor()
	#Deal with LotW first, each locator I used must be uploaded seperately
	c.execute("SELECT DISTINCT MyGridSquare FROM log WHERE LotwQslSent = 'N'")
	locators = c.fetchall() # Locators now contains all the locators with un-uploaded QSOs
	if(locators == ()):
		print("Nothing to upload to LoTW for {}".format(callsign))
		return 0

	for locator in locators: #For each locator
		print("Uploading log from {} in locator {}".format(callsign, locator[0]))
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


		#Get my CQ Zone, DXCC number and ITU Zone from locations file
		#and write station information to LoTW config file
		locatorFile = open("/home/pi/.tqsl/station_data", "w")
		locatorFile.write("<StationDataFile>\n")
		locatorFile.write("  <StationData name=\"test\">\n")
		locatorFile.write("    <CALL>{}</CALL>\n".format(callsign))
		locatorFile.write("    <CQZ>{}</CQZ>\n".format(location.locations[callsign].cqz))
		locatorFile.write("    <DXCC>{}</DXCC>\n".format(location.locations[callsign].dxcc))
		locatorFile.write("    <GRIDSQUARE>{}</GRIDSQUARE>\n".format(locator[0]))
		locatorFile.write("    <ITUZ>{}</ITUZ>\n".format(location.locations[callsign].itu))
		locatorFile.write("  </StationData>\n")
		locatorFile.write("</StationDataFile>\n")
		locatorFile.close()

		#Upload the ADIF to LoTW
		print("\n\n")
		lotwResult = subprocess.call(["tqsl", "-a", "abort", "-d", "-l", "test", "-u", "-x", "/tmp/log.adi"], stderr = subprocess.DEVNULL)
		print("\n\n")

		#Check error code
		if(lotwResult == 0):
			c.execute("UPDATE log SET LotwQslSent = 'Y' WHERE MyGridSquare = %s AND LotwQslSent = 'N'", (locator[0],)) #All fine, update log
			db.commit()
		elif(lotwResult == 1): print("Cancelled by user")
		elif(lotwResult == 2): print("Rejected by LoTW")
		elif(lotwResult == 3): print("Unexpected Response from TQSL Server")
		elif(lotwResult == 4): print("TQSL Error, suspect Xvfb has not been setup")
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

def guess_blank_dxcc(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1

	c = db.cursor()
	c.execute("SELECT `Call` FROM log WHERE Dxcc = ''")
	callsigns = c.fetchall()
	if(callsigns == ()):
		print("No tidying required for {}".format(callsign))
		db.close()
		return 0

	else:
		errorCode = 0
		for call in callsigns: #I know the helpage says don't iterate but there shouldn't be many
			url = 'https://clublog.org/dxcc'
			payload = {'call' : call[0], 'api' : passwords.CLUBLOG_API_KEY, 'full' : '1'}
			result = requests.get(url, payload)
			if(result.status_code != 200):
				print("Error downloading data from Clublog for callsign {}".format(call))
				return 2
			info = json.loads(result.text)
			if(info['DXCC'] == 0):
				print("No DXCC found for {}".format(call[0]))
				errorCode = 2
			else:
				print("Updating {} to Country: {}".format(call[0], info['Name']))
				c.execute("UPDATE log SET Dxcc = %s, Country = %s WHERE `Call` = %s", (info['DXCC'], info['Name'].title(), call))
		db.commit()
		db.close()
		return errorCode


#Puts the default locator in for each callsign
#returns	0 - Success
#		1 - SQL Error
#		2 - No default locator for the callsign
def guess_my_locator(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1
	c = db.cursor()

	#Check we have a default locator for this callsign
	try:
		x = location.default_locator[callsign]
	except KeyError:
		print("No default locator found for {}".format(callsign))
		return 2

	#Default locator found so update log
	c.execute("UPDATE log SET MyGridSquare = %s WHERE MyGridSquare = ''", (location.default_locator[callsign],))
	print("Blank locators for {} replaced with {}".format(callsign, location.default_locator[callsign]))
	db.commit()
	db.close()
	return 0


if __name__ == '__main__':
	guess_blank_dxcc("M0WUT")
	guess_my_locator("M0WUT")
	lotw_upload("M0WUT")
	lotw_download("M0WUT")
	clublog_upload("M0WUT")
