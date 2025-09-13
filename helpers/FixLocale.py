from pathlib import Path
from colorama import Fore, Back, Style
import colorama
import xmltodict
import json
import os

class FixLocale():
	def fix(self, file, conv):
		try:
			data = conv.readxml(file)
			dupes = 0
			vfix = 0
			db = {}
			construct = []

			# Fix dupes
			for x in data["contentList"]["content"]:
				if not x['@contentuid'] in db.keys():
					construct.append(x)
					db[x['@contentuid']] = x['@version']
					continue
				dupes += 1
				#print(x['@contentuid'])
				if int(x['@version']) > int(db[x['@contentuid']]):
					db[x['@contentuid']] = x['@version']

			# Set Versions all to 1
			for x in construct:
				if x['@version'] != '1':
					vfix += 1
				x['@version'] = '1'

			data["contentList"]["content"] = construct
			conv.writexml(data, str(file).replace('.xml', '_fix.xml'))
			print(f'{Fore.GREEN}[locale] Fixed {os.path.basename(file)} (Duplicates: {dupes}; Version Resets: {vfix}){Fore.WHITE}')
			return True
		except Exception as e:
			return False
