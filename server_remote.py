#!/usr/bin/env python3

import doglcd, datetime, time
import subprocess
import os, sys
import callsigns
import sql_handler
from xvfbwrapper import Xvfb

####################################################
#Callsigns to be handled should be in 'callsigns.py#
####################################################

##################
##Initialisation##
##################

#Blink LED to show program started
print("MySQL LogHandler v0.1 - M0WUT and M0IKY")

#Ensure there is a passwords file present
try:
	import passwords
except:
	print("No passwords file found. Copy passwords_EXAMPLE.py to passwords.py and input information")
	sys.exit()


#########################
#Synchronise everything##
#########################
with Xvfb() as xvfb:
	errorCode, callsign = sql_handler.handle_everything()
	if errorCode != 0:
		print("Error code {} when handling {}'s log".format(errorCode, callsign))







