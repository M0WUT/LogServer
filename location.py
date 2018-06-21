#Class containing location information for each callsign
class location:
	def __init__(self, dxcc, itu, cqz):
		self.dxcc = dxcc
		self.itu = itu
		self.cqz = cqz


#Information for each country
england = location(223, 27, 14)


#Dictionary mapping each callsign to its information, a callsign in this dictionary expect a valid TQSL certificate in ~/LotW/Certificates
locations = {	'M0WUT' : england,
		'M0WUT/P' : england
}
