#!/usr/bin/env python3

import doglcd, datetime, time
import subprocess
import os, sys
import RPi.GPIO as GPIO
import callsigns
import sql_handler

#Syncs all callsigns in callsigns.callsigns_list()
#Returns:	0 - Success
#		1 - Callsign not in callsigns_list (should be impossible as callsigns are generated from callsigns_list)
#		2 - Error connecting to SQL database
#		3 - Error downloading QSLs from LoTW
#		4 - LoTW QSL not found in log
#		5 - Error requesting data from Clublog
#		6 - TQSL Error: Cancelled by User
#		7 - TQSL Error: Rejected by LoTW
#		8 - TQSL Error: Unexpected response from LoTW server
#		9 - TQSL Error: TQSL Error
#		10 - TQSL Error: TQSLlib Error
#		11 - TQSL Error: Unable to open input file
#		12 - TQSL Error: Unable to open output file
#		13 - TQSL Error: All QSOs wer duplicates or out of range
#		14 - TQSL Error: Some QSOs were duplicates or out of range
#		15 - TQSL Error: Command Syntax Error
#		16 - TQSL Error: LoTW Connection Error
#		17 - Callsign not recognised by Clublog


def handle_everything():
	try:
		file = open('synctime.txt', 'r')
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
		errorCode = sql_handler.guess_blank_dxcc(callsign)

		if(errorCode == 0): pass
		else: return(errorCode, callsign)

		#Fill in any QSO where my locator hasn't been specified with the default from 'callsigns.py'
		lcd.clear_line(2)
		lcd.write(2, 0, "Updating locator")
		errorCode = sql_handler.fill_my_locator(callsign)

		if(errorCode == 0): pass
		else: return(errorCode, callsign)

		#Upload any new QSOs to LoTW
		lcd.clear_line(2)
		lcd.write(2, 1, "LoTW Uploading")
		sql_handler.lotw_upload(callsign)

		if(errorCode == 0): pass
		else: return(errorCode, callsign)

		#Download any new QSLs from LoTW
		lcd.clear_line(2)
		lcd.write(2, 0, "LoTW Downloading")
		sql_handler.lotw_download(callsign, lastSyncTime)

		if(errorCode == 0): pass
		else: return(errorCode, callsign)

		#Upload any new QSOs to Clublog
		sql_handler.clublog_upload(callsign)
		lcd.clear_line(2)
		lcd.write(2, 1, "Clublog upload")

		if(errorCode == 0): pass
		else: return(errorCode, callsign)

	#Save sync time to file
	syncTime = time.strftime('%Y-%m-%d %H:%M', time.gmtime())
	returnTime = time.strftime('%d-%m-%Y %H:%M', time.gmtime())

	file = open("synctime.txt", "w")
	file.write(syncTime)
	file.close()
	lcd.clear()
	return(0, returnTime)


####################################################
#Callsigns to be handled should be in 'callsigns.py#
####################################################

#Config settings
LED = 21
LCD_CONTRAST = 12

##################
##Initialisation##
##################

# Setup LCD
lcd = doglcd.DogLCD(10, 11, 25, -1, -1, -1) #(SI, CLK, RS, RSB, Reset, Backlight)
lcd.begin(doglcd.DOG_LCD_M163, LCD_CONTRAST)

#Setup warning LED
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED, GPIO.OUT)

#Get IP address to display on startup (Has saved me on many occassions!)
ip = subprocess.check_output(['hostname', '-I']) \
			.decode('ascii') \
			.strip() \
			.split(' ')[0] \
			.center(16, ' ') #Pad with spaces to center on 16 character LCD

#Startup message
lcd.write(0,0, " Log4OM Handler    M0WUT 6/18")
lcd.write(2,0, ip)

#Blink LED to show program started
for i in range(5):
	GPIO.output(21, GPIO.HIGH)
	time.sleep(0.5)
	GPIO.output(21, GPIO.LOW)
	time.sleep(0.5)

#Ensure there is a passwords file present
try:
	import passwords
except:
	print("No passwords file found. Copy passwords_EXAMPLE.py to passwords.py and input information")
	sys.exit()


##################################################################################
#Main loops, tries to synchronise everything and then sleeps for 15 minutes (ish)#
##################################################################################
while(1):
	lcd.clear()
	errorCode, callsign = handle_everything()
	lcd.clear()
	callsign = callsign.center(16, ' ')

	if(errorCode == 0):
		lcd.write(0,0, ip)
		lcd.write(1,1, "Last synced at")
		lcd.write(2,0, callsign) #In the case of success, callsign contains the sync time
	elif(errorCode == 2): lcd.write(0,0, "Error connecting  to MySQL for  " + callsign)
	elif(errorCode == 3): lcd.write(0,0, " LoTW Download     error for:   " + callsign)
	elif(errorCode == 4): lcd.write(0,0, "  LoTW QSL not    found in log  " + callsign)
	elif(errorCode == 5): lcd.write(0,0, "Clublog Request      error      " + callsign)
	elif(errorCode == 17): lcd.write(0,0, "  Unrecognised  callsign in log:" + callsign)
	else:
		lcd_write(0,0, "   TQSL Error        in log     " + callsign)










	#Wait for 15 minutes
	if(errorCode == 0):
		time.sleep(15*60)
	else:
		for i in range(15*30): #Each loop takes 2 seconds
			GPIO.output(LED, GPIO.HIGH)
			time.sleep(1)
			GPIO.output(LED, GPIO.LOW)
			time.sleep(1)








