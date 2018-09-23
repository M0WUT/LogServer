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

#Setup fake framebuffer for TQSL
try:
	x=os.environ['DISPLAY'] #See if framebuffer running
except KeyError:
	subprocess.call(["/home/pi/LogServer/fake_framebuffer.sh"]) #if not, start fake one

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
	errorCode, callsign = sql_handler.handle_everything(lcd)
	lcd.clear()
	lcd.write(2, 0, ip) #Always show IP
	if(errorCode == 0):
		lcd.write(0,0, ip)
		lcd.write(1,1, "Last synced at")
		lcd.write(2,0, callsign) #In the case of success, callsign contains the sync time
	elif(errorCode == 2): lcd.write(0,0, "MySQL Error for:" + callsign)
	elif(errorCode == 3): lcd.write(0,0, " LoTW Download  Error:" + callsign)
	elif(errorCode == 4): lcd.write(0,0, "LoTW QSL not in log:  " + callsign)
	elif(errorCode == 5): lcd.write(0,0, "Clublog Request Error:" + callsign)
	elif(errorCode == 18): lcd.write(0,0, "Bad DXCC in log:" + callsign)
	else:
		lcd.write(0,0, " TQSL Error in: " + callsign)



	#Wait for 15 minutes
	if(errorCode == 0):
		time.sleep(15*60)
	else:
		for i in range(15*30): #Each loop takes 2 seconds
			GPIO.output(LED, GPIO.HIGH)
			time.sleep(1)
			GPIO.output(LED, GPIO.LOW)
			time.sleep(1)








