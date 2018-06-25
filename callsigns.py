#Class containing location information for each callsign
class location:
	def __init__(self, dxcc, itu, cqz, defaultGridsquare):
		self.dxcc = dxcc
		self.itu = itu
		self.cqz = cqz
		self.defaultGridsquare  = defaultGridsquare


#Information for each country
england = location(223, 27, 14, 'JO02AF')
st_pierre_et_miquelon = location(277, 9, 5, 'GN16WS')

#Map each callsign to it's location. Each callsign in this lists expects a LoTW certificate loaded into TQSL 
#Also requres a  MySQL database named the callsign with any '/' replaced with '_' e.g. FP/M0WUT -> FP_M0WUT

locations = 	{
			'M0WUT' : england
			#'FP/M0WUT' : st_pierre_et_miquelon
		}


def callsign_list():
	return list(locations.keys())

if __name__ == '__main__':
	print(callsign_list())

