#!/usr/bin/python3

import passwords
import MySQLdb
import sys
import requests


#Uploads any new QSOs to LotW and Clublog
#Expects MySQL database to have same name as callsign
def upload_new_QSO(callsign):
	try:
		db = MySQLdb.connect(	host = passwords.SQL_SERVER,
					user = passwords.SQL_USERNAME,
					passwd = passwords.SQL_PASSWORD,
					port = passwords.SQL_PORT,
					db = callsign)
		print("Connected to {} database".format(callsign))

	except:
		print("Failed to connect to SQL database for {} on {}:{}".format(callsign, passwords.SQL_SERVER, passwords.SQL_PORT))
		return 1;

	c = db.cursor()
	#Deal with LotW first, each locator I used must be uploaded seperately
	c.execute("SELECT DISTINCT MyGridSquare FROM log WHERE LotwQslSent = 'N'")
	locators = c.fetchall() # Locators now contains all the locators with un-uploaded QSOs
	for locator in locators: #For each locator
		print("Uploading callsign from {} in locator {}".format(callsign, locator[0]))
		#Get all of the QSOs that haven't been uploaded yet
		c.execute("SELECT QsoDate, TimeOn, Freq, Band, Mode, `Call`, RstSent, RstRcvd FROM log WHERE LotwQslSent = 'N' AND MyGridSquare = %s ORDER BY QsoDate, TimeOn", (locator[0],))
		qsos = c.fetchall();
		logfile = open ("/ramdisk/log.adi", "w");
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
		MyDxcc = requests.get(url, payload).text
		print(MyDxcc)
		


if __name__ == '__main__':
	upload_new_QSO("M0WUT")

