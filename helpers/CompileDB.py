from pathlib import Path
import xmltodict
import json
import os

class CompileDB():
	data = None
	file = None
	db = None
	auxdb = None
	bgpath = None

	def __init__(self, bgpath=None):
		self.bgpath = bgpath

	def compile(self):
		self.db = {"LSX":{},"Stats":{},"DataTypes":{"EnumTypes":{}}}

		if not self.bgpath is None:
			rec = f'{self.bgpath}/Data/Editor/Mods/.'
		else:
			rec = '.'

		for file in Path(rec).rglob('*.*'):
			self.file = file
			fname, fext = os.path.splitext(file)
			fname = os.path.basename(fname)

			if (fext != '.tbl' and fext != '.stats') or self.is_file_guid(fname):
				continue
			try:
				self.data = self.readxml(str(file))
				if fext == ".tbl":
					self.db['LSX'][fname] = self.data['stats']['@stat_object_definition_id']
				elif fext == ".stats":
					self.db['Stats'][fname] = self.data['stats']['@stat_object_definition_id']

				builder = self.data['stats']['stat_objects']['stat_object']
				if not isinstance(builder, list):
					builder = [builder]
				for node in builder:
					for subnode in node['fields']['field']:
						self.db['DataTypes'][subnode['@name']] = subnode['@type']
						if subnode['@type'] == 'EnumerationTableFieldDefinition':
							self.db['DataTypes']['EnumTypes'][subnode['@name']] = subnode['@enumeration_type_name']

				print(f'Compiled {file}')
			except Exception as e:
				if str(e) != "'NoneType' object is not subscriptable":
					print(f'Failed to compile {os.path.basename(file)}:\n\t{e}')

		print(f'\nCompile Completed')
		with open(f'./db.json', 'w') as f:
			f.write(json.dumps(self.db, indent=4))

	# Compile auxiliary db for parent IDs at runtime
	def compileAuxiliaryDB(self, append=None):
		self.auxdb = {}
		if not append is None:
			self.auxdb = append

		if not self.bgpath is None:
			rec = f'{self.bgpath}/Data/Editor/Mods/.'
		else:
			rec = '.'

		for file in Path(rec).rglob('*.*'):
			fname, fext = os.path.splitext(file)
			fname = os.path.basename(fname)

			if (fext != '.tbl' and fext != '.stats') or self.is_file_guid(fname):
				continue
			try:
				self.data = self.readxml(str(file))
				builder = self.data['stats']['stat_objects']['stat_object']
				if not isinstance(builder, list):
					builder = [builder]
				for node in builder:
					uuid = ''
					name = ''
					for subnode in node['fields']['field']:
						if subnode['@name'] == 'Name':
							if fname == "Projectile" or fname == "Target" or fname == "Zone" or fname == "Shout" or fname == "ProjectileStrike" or fname == "Rush" or fname == "Teleportation" or fname == "Throw":
								name = f'{fname}_{subnode["@value"]}'
							else:
								name = subnode['@value']
						if subnode['@name'] == 'UUID':
							uuid = subnode['@value']
						if name != '' and uuid != '':
							if self.auxdb.get(name,'') != '':
								break
							self.auxdb[name] = uuid
							break
			except Exception as e:
				pass

		print(f'Compiling Auxiliary DB Completed\n')
		with open(f'./auxdb.json', 'w') as f:
			f.write(json.dumps(self.auxdb, indent=4))

		return self.auxdb

	# Read data from xml file
	def readxml(self, file):
		with open(file, 'r+b') as f:
			data = xmltodict.parse(f.read())
		return data

	def is_file_guid(self, file):
		if len(file) == 36 and file[8:9:] == "-" and file[13:14:] == "-" and file[18:19:] == "-" and file[23:24:] == "-":
			return True
		return False

if __name__ == "__main__":
	cdb = CompileDB()
	cdb.compile()
