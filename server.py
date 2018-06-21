#!/usr/bin/env python3

import doglcd, datetime, time
import MySQLdb
import passwords


######################
##LCD Initialisation##
######################

# __init__(self, lcdSI, lcdCLK, lcdRS, lcdCSB, pin_reset, pin_backlight):
lcd = doglcd.DogLCD(10,11,25,8,-1,-1)
lcd.begin(doglcd.DOG_LCD_M163, 12)
lcd.write(0,0, "Hello world")


