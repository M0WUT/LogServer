#!/usr/bin/env python3

import doglcd, datetime, time
import subprocess
import os, sys
import RPi.GPIO as GPIO
import callsigns
import sql_handler


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
		elif(errorCode == 1):
			lcd.write(0,0, "Unhandled Call: ")
			lcd.write(1,0, callsign)
			break
		elif(errorCode == 2):
			lcd.write(0,1, "SQL Error for:")
			lcd.write(1,0, callsign)
			break

		#Fill in any QSO where my locator hasn't been specified with the default from 'callsigns.py'
		lcd.clear_line(2)
		lcd.write(2, 0, "Updating locator")
		errorCode = sql_handler.fill_my_locator(callsign)

		if(errorCode == 0): pass
		elif(errorCode == 1):
			lcd.write(0,0, "Unhandled Call: ")
			lcd.write(1,0, callsign)
			break
		elif(errorCode == 2):
			lcd.write(0,1, "SQL Error for:")
			lcd.write(1,0, callsign)
			break

		#Upload any new QSOs to LoTW
		lcd.clear_line(2)
		lcd.write(2, 1, "LoTW Uploading")
		sql_handler.lotw_upload(callsign)

		if(errorCode == 0): pass
		elif(errorCode == 1):
			lcd.write(0,0, "Unhandled Call: ")
			lcd.write(1,0, callsign)
			break
		elif(errorCode == 2):
			lcd.write(0,1, "SQL Error for:")
			lcd.write(1,0, callsign)
			break

		#Download any new QSLs from LoTW
		lcd.clear_line(2)
		lcd.write(2, 0, "LoTW Downloading")
		sql_handler.lotw_download(callsign, lastSyncTime)

		if(errorCode == 0): pass
		elif(errorCode == 1):
			lcd.write(0,0, "Unhandled Call: ")
			lcd.write(1,0, callsign)
			break
		elif(errorCode == 2):
			lcd.write(0,1, "SQL Error for:")
			lcd.write(1,0, callsign)
			break
		break
		#Upload any new QSOs to Clublog
		sql_handler.clublog_upload(callsign)
		lcd.clear_line(2)
		lcd.write(2, 1, "Clublog upload")
		if(errorCode == 0): pass
		elif(errorCode == 1):
			lcd.write(0,0, "Unhandled Call: ")
			lcd.write(1,0, callsign)
			break
		elif(errorCode == 2):
			lcd.write(0,1, "SQL Error for:")
			lcd.write(1,0, callsign)
			break




	#lcd.clear()
	time.sleep(15*60)







