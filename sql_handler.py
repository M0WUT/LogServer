#!/usr/bin/python3

import callsigns
import passwords
import MySQLdb
import sys
import requests
import subprocess
import json
import re #Regular expression library
import time
import os


#Downloads all QSL request from clublog since 'lastSyncTime' for callsign
#Expected lastSyncTime format 1945-01-27 12:34:00
#Returns	0 - Success
#		1 - Callsign not in callsigns_list
#		2 - Error connecting to MySQL database
#		5 - Error requesting data from Clublog
def oqrs_download(callsign, lastSyncTime):

	#Check we are setup to handle this callsign
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1

	#Open MySQL database
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'),
					client_flag = 2) #so rowcount returns matched rows rather than updated rows

	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2

	c = db.cursor()


	url = "https://clublog.org/getadif.php"
	year = lastSyncTime[:4]
	month = lastSyncTime[5:7]
	day = lastSyncTime[8:10]
	values = {'email' : passwords.CLUBLOG_EMAIL, 'password' : passwords.CLUBLOG_APPLICATION_PASSWORD, 'call' : callsign, 'type' : 'dxqsl', 'startyear' : year, 'startmonth' : month, 'startday' : day}
	result = requests.post(url, data=values)
	if(result.status_code != 200):
		print("Error downloading data from Clublog for callsign {}".format(call))
		return 5
	log = result.text
	logbook = adif_to_dictionary(log)
	errors = 0

	for qso in logbook:
		c.execute("UPDATE log SET QslSent = %s, QslSentVia = %s, QslSDate = %s, Address = %s WHERE `Call` = %s AND Band = %s AND Mode = %s AND QsoDate = %s AND TimeOn LIKE %s", \
				(qso['qsl_sent'], qso['qsl_sent_via'] if 'qsl_sent_via' in qso else('D' if 'address' in qso else 'B'), \
				qso['qslsdate'] if 'qslsdate' in qso else '', \
				(qso['call'] + ', ' + qso['address']).replace(', ', '\r\n').replace(',', '\r\n') if 'address' in qso else '', qso['call'], qso['band'], qso['mode'], qso['qso_date'], qso['time_on'][:4]+'%'))
		if(c.rowcount != 1):
			errors += 1
			print("No match found for {} in QSO with {} on {} {}, {} {}".format(callsign, qso['call'], qso['qso_date'], qso['time_on'], qso['band'], qso['mode']))

	print("{} OQRS requests downloaded for {}".format(len(logbook) - errors, callsign))

	db.commit()
	db.close()

#Syncs all callsigns in callsigns.callsigns_list()
#Returns:       0 - Success
#               1 - Callsign not in callsigns_list (should be impossible as callsigns are generated from callsigns_list)
#               2 - Error connecting to SQL database
#               3 - Error downloading QSLs from LoTW
#               4 - LoTW QSL not found in log
#               5 - Error requesting data from Clublog
#               6 - TQSL Error: Cancelled by User
#               7 - TQSL Error: Rejected by LoTW
#               8 - TQSL Error: Unexpected response from LoTW server
#               9 - TQSL Error: TQSL Error
#               10 - TQSL Error: TQSLlib Error
#               11 - TQSL Error: Unable to open input file
#               12 - TQSL Error: Unable to open output file
#               13 - TQSL Error: All QSOs wer duplicates or out of range
#               14 - TQSL Error: Some QSOs were duplicates or out of range
#               15 - TQSL Error: Command Syntax Error
#               16 - TQSL Error: LoTW Connection Error
#		17 - TQSL Error: Unknown, most likely framebuffer not set
#               18 - Callsign not recognised by Clublog


def handle_everything(lcd):
	try:
		file = open('/home/pi/LogServer/synctime.txt', 'r')
		lastSyncTime = file.read()
		file.close()
	except:
		lastSyncTime = "1945-01-01 00:00:00"

	lcd.clear()
	for callsign in callsigns.callsign_list():

		lcd.clear()
		lcd.write(0,2, "Processing:")
		lcd.write(1,0, callsign)

		#Fill in any blank dxcc fields
		lcd.clear_line(2)
		lcd.write(2, 1, "Checking DXCCs")
		errorCode = guess_blank_dxcc(callsign)

		if(errorCode != 0): return(errorCode, callsign)


		#Fill in any QSO where my locator hasn't been specified with the default from 'callsigns.py'
		lcd.clear_line(2)
		lcd.write(2, 0, "Updating locator")
		errorCode = fill_my_locator(callsign)

		if(errorCode != 0): return(errorCode, callsign)


		#Upload any new QSOs to LoTW
		lcd.clear_line(2)
		lcd.write(2, 1, "LoTW Uploading")
		errorCode = lotw_upload(callsign)

		if(errorCode != 0): return(errorCode, callsign)


		#Download any new QSLs from LoTW
		lcd.clear_line(2)
		lcd.write(2, 0, "LoTW Downloading")
		errorCode = lotw_download(callsign, lastSyncTime)

		if(errorCode != 0): return(errorCode, callsign)


		#Upload any new QSOs to Clublog
		lcd.clear_line(2)
		lcd.write(2, 1, "Clublog upload")
		errorCode = clublog_upload(callsign)

		if(errorCode != 0): return(errorCode, callsign)


		#Download any new OQRS request
		lcd.clear_line(2)
		lcd.write(2, 0, "OQRS Downloading")
		errorCode = oqrs_download(callsign, lastSyncTime)

		if(errorCode != 0): return(errorCode, callsign)

	#Save sync time to file
	syncTime = time.strftime('%Y-%m-%d %H:%M', time.gmtime())
	returnTime = time.strftime('%d-%m-%Y %H:%M', time.gmtime())

	file = open("/home/pi/LogServer/synctime.txt", "w")
	file.write(syncTime)
	file.close()
	lcd.clear()
	return(0, returnTime)



#Converts an ADIF file to an array of qsos, with each qso being a dictionary
def adif_to_dictionary(adif):
#Code for ADIF parsing heavily based on code from  OK4BX: (http://web.bxhome.org/blog/ok4bx/2012/05/adif-parser-python)
	raw = re.split('<eoh>|<eor>(?i)', adif) #Split on <eoh> or <eor>, case insensitive
	raw.pop(0) #Remove header
	raw.pop() #Remove End of File junk
	logbook = []
	for record in raw:
		qso = {}
		tags = re.findall('<(.*?):(\d+).*?>([^<\r\n]+)',record)
		for tag in tags:
			qso[tag[0].lower()] = tag[2].upper()
		logbook.append(qso)
	return logbook


#Downloads any new QSLs from LoTW and updates log, sets ClublogQsoUploadStatus back to 'N' for any records changed
#return		0 - Success
#		1 - Callsign not in 'callsigns.py'
#		2 - SQL Error
#		3 - LoTW Download Error
#		4 - Unmatched QSL found in downloaded log
def lotw_download(callsign, lastSyncTime):

	#Check we are setup to handle this callsign
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1


	url = "https://lotw.arrl.org/lotwuser/lotwreport.adi"
	values = {'login' : passwords.LOTW_USERNAME, 'password' : passwords.LOTW_PASSWORD, 'qso_query' : '1', 'qso_qsl' : 'yes', 'qso_qslsince' : lastSyncTime, 'qso_owncall' : callsign}

	result = requests.get(url,values)
	log = result.text
	if(result.status_code != 200):
		print("Error downloading data from LoTW")
		return 3

	logbook = adif_to_dictionary(log)

	#Update MySQL database
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'),
					client_flag = MySQLdb.constants.CLIENT.FOUND_ROWS) #so rowcount returns matched rows rather than updated rows
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2

	c = db.cursor()
	errors = 0
	for qso in logbook:
		try:	#Set Clublog upload status to no so it's re-uploaded showing confirmed
			c.execute("UPDATE log SET LotwQslRcvd = 'Y', ClublogQsoUploadStatus = 'N' WHERE `Call` = %s AND Band = %s AND Mode = %s AND QsoDate = %s AND TimeOn LIKE %s", (qso['call'], qso['band'], qso['mode'], qso['qso_date'], (qso['time_on'][:-2] + '%')))
		except KeyError:
			print("No callsign found in record:")
			print(qso)
			errors += 1

		if(c.rowcount != 1):
			errors += 1
			print('No record found in {}\'s log for {} at {} on {}, {} {}'.format(callsign, qso['call'], qso['time_on'], qso['qso_date'], qso['band'], qso['mode']))
	print("{} QSLs for {}  downloaded from LoTW since {}, {} records updated in log".format(len(logbook), callsign, lastSyncTime, len(logbook) - errors))
	db.commit()

	if(errors == 0): return 0
	else: return 4


#Uploads any new QSOs for 'callsign' to Clublog
#Assumes MySQL database has same name as callsign
#returns 	0 - Success
#		1 - Callsign not found in 'callsign.py'
#		2 - SQL Error
#		5 - Clublog Error
def clublog_upload(callsign):

	#Check we are setup to handle this callsign
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1

	#Attempt to connect to MySQL database for that callsign
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'))
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2

	c = db.cursor()
	c.execute("SELECT QsoDate, TimeOn, Freq, Band, Mode, `Call`, RstSent, RstRcvd, LotwQslRcvd, QslSent FROM log WHERE ClublogQsoUploadStatus = 'N' ORDER BY QsoDate, TimeOn")
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
		logfile.write("<QSO_DATE:8>{} <TIME_ON:6>{} <FREQ:{}>{} <BAND:{}>{} <MODE:{}>{} <CALL:{}>{} <RST_SENT:{}>{} <RST_RCVD:{}>{} <LOTW_QSL_RCVD:1>{} <QSL_SENT:1>{} <EOR>\r\n".format(qso[0], qso[1], len(freq), freq, len(qso[3]), qso[3], len(qso[4]), qso[4], len(qso[5]), qso[5], len(qso[6]), qso[6], len(qso[7]), qso[7], qso[8], qso[9]))
	logfile.close()

	#Now have ADIF file ready for upload to Clublog
	url = "https://clublog.org/putlogs.php"
	files = {'file' : open("/tmp/log.adi", "r")}
	values = {'email' : passwords.CLUBLOG_EMAIL, 'password' : passwords.CLUBLOG_APPLICATION_PASSWORD, 'callsign' : callsign, 'api' : passwords.CLUBLOG_API_KEY}
	request = requests.post(url, files=files, data=values)
	errorCode = request.status_code
	if(errorCode == 200):
		print("Uploaded QSOs for {} to Clublog".format(callsign))
		c.execute("UPDATE log SET ClublogQsoUploadStatus = 'Y' WHERE ClublogQsoUploadStatus = 'N'")
		db.commit()
		print("QSOs for {} successfully uploaded to Clublog".format(callsign))
		return 0
	else:
		print("Clublog Upload for {} failed. Error {}: ".format(callsign, errorCode, request.text))
		return 5



#Uploads any new QSOs for 'callsign' to LoTW
#Expects MySQL database to have same name as callsign with any '/' replaced with '_'

#returns	0 - Success - Either nothing to do or all fine
#		1 - Callsign not found in 'callsigns.py'
#		2 - SQL Error
#		6 - Cancelled by User
#		7 - Rejected by LoTW
#		8 - Unexpected response from TQSL server
#		9 - TQSL error
#		10 - TQSLlib error
#		11 - Unable to open input file
#		12 - Unable to open output file
#		13 - All QSOs were duplicates or out of range
#		14 - Some QSOs were duplicates or out of range
#		15 - Command Syntax Error
#		16 - LoTW Connection Error
#		17 - Unknown TQSL error, most likely no framebuffer set

def lotw_upload(callsign):

	#Check we are setup to handle this callsign
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1

	#Attempt to connect to MySQL database for that callsign
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'))
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2

	c = db.cursor()
	#Deal with LotW first, each locator used must be uploaded seperately
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
		locatorFile.write("    <CQZ>{}</CQZ>\n".format(callsigns.locations[callsign].cqz))
		locatorFile.write("    <DXCC>{}</DXCC>\n".format(callsigns.locations[callsign].dxcc))
		locatorFile.write("    <GRIDSQUARE>{}</GRIDSQUARE>\n".format(locator[0]))
		locatorFile.write("    <ITUZ>{}</ITUZ>\n".format(callsigns.locations[callsign].itu))
		locatorFile.write("  </StationData>\n")
		locatorFile.write("</StationDataFile>\n")
		locatorFile.close()

		#Upload the ADIF to LoTW
		print("\n\n")
		lotwResult = subprocess.call(["tqsl", "-a", "abort", "-d", "-l", "test", "-u", "-x", "/tmp/log.adi"])
		print("\n\n")

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
		else:
			print("Unknown TQSL Error, most likely Framebuffer not set")
			lotwResult = 12
		#If not success, cancel everything and return
		if(lotwResult != 0): return (lotwResult + 5) #(+2) as smaller value error codes are taken are reserved for success, callsign not found and SQL error respectively in this program

	db.close()
	return 0

#If any fields have blank DXCC entries, ask Clublog and update them
#returns	0 - success - either nothing to do or all done fine
#		1 - Callsign not found in 'callsigns.py'
#		2 - SQL Error
#		5 - Clublog Error - either connection not valid or callsign not recognised
#		18 - Clublog not recognising callsign

def guess_blank_dxcc(callsign):
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1

	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'))
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2

	c = db.cursor()
	c.execute("SELECT `Call` FROM log WHERE Dxcc = ''")
	callsignsToUpdate = c.fetchall()
	if(callsignsToUpdate == ()):
		db.close()
		return 0

	else:
		errorCode = 0
		for call in callsignsToUpdate: #I know the helpage says don't iterate but there shouldn't be many
			url = 'https://clublog.org/dxcc'
			payload = {'call' : call[0], 'api' : passwords.CLUBLOG_API_KEY, 'full' : '1'}
			result = requests.get(url, payload)
			if(result.status_code != 200):
				print("Error downloading data from Clublog for callsign {}".format(call))
				return 5
			info = json.loads(result.text)
			if(info['DXCC'] == 0):
				print("No DXCC found for {}".format(call[0]))
				errorCode = 18
			else:
				print("Updating {} to Country: {}".format(call[0], info['Name']))
				c.execute("UPDATE log SET Dxcc = %s, Country = %s WHERE `Call` = %s", (info['DXCC'], info['Name'].title(), call))
		db.commit()
		db.close()
		return errorCode


#Puts the default locator in for each callsign
#returns	0 - Success
#		1 - SQL Error
#		2 - 'callsigns.py' not setup to handle supplied callsign
def fill_my_locator(callsign):
	if(callsign not in callsigns.callsign_list()):
		print("Not setup to handle callsign: {}".format(callsign))
		return 1
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign.replace('/', '_'))
	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 2
	c = db.cursor()

	#Default locator found so update log
	c.execute("UPDATE log SET MyGridSquare = %s WHERE MyGridSquare = ''", (callsigns.locations[callsign].defaultGridsquare,))
	if(c.rowcount > 0): print("Blank locators for {} replaced with {}".format(callsign, callsigns.locations[callsign].defaultGridsquare))
	db.commit()
	db.close()
	return 0



if(__name__ == '__main__'):
	oqrs_download("M0WUT", "1945-01-23 12:34")
