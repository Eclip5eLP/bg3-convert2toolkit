from pathlib import Path
import xmltodict
import json
import os
import sys

from helpers.Schema import compile_schema, REFERENCE_PROJECTS

SPELL_TYPES = ["Projectile", "ProjectileStrike", "Rush", "Shout", "Target", "Teleportation", "Throw", "Wall", "Zone"]


class CompileDB():
	data = None
	file = None
	db = None
	auxdb = None
	bgpath = None

	def __init__(self, bgpath=None, root_path=None):
		self.bgpath = bgpath
		self.root_path = Path(root_path) if root_path is not None else Path('.')

	def editor_mods(self) -> Path:
		if not self.bgpath is None:
			return Path(f'{self.bgpath}/Data/Editor/Mods')
		return Path('.')

	def compile(self):
		# Keep hand maintained parts of the existing db (e.g. EnumSubTypes)
		try:
			with open(self.root_path / 'db.json', encoding='utf-8') as f:
				self.db = json.load(f)
		except FileNotFoundError:
			self.db = {}
		self.db.setdefault("LSX", {})
		self.db.setdefault("Stats", {})
		self.db.setdefault("DataTypes", {"EnumTypes": {}})
		self.db["DataTypes"].setdefault("EnumTypes", {})

		for file in self.editor_mods().rglob('*.*'):
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
					fields = node['fields']['field']
					for subnode in fields if isinstance(fields, list) else [fields]:
						self.db['DataTypes'][subnode['@name']] = subnode['@type']
						if subnode['@type'] == 'EnumerationTableFieldDefinition':
							self.db['DataTypes']['EnumTypes'][subnode['@name']] = subnode['@enumeration_type_name']

				print(f'Compiled {file}')
			except Exception as e:
				if str(e) != "'NoneType' object is not subscriptable":
					print(f'Failed to compile {os.path.basename(file)}:\n\t{e}')

		# Field definitions of the toolkit itself
		if not self.bgpath is None:
			self.db['Schema'] = compile_schema(self.bgpath)

		print(f'\nCompile Completed')
		with open(self.root_path / 'db.json', 'w', encoding='utf-8') as f:
			f.write(json.dumps(self.db, indent=4))

	# Compile auxiliary db for parent IDs at runtime
	def compileAuxiliaryDB(self, append=None):
		self.auxdb = {}
		if not append is None:
			self.auxdb = append

		# Larian's projects first, so vanilla names resolve to vanilla entries and not to overrides of other mods
		editor_mods = self.editor_mods()
		projects = [p for p in editor_mods.iterdir() if p.is_dir()] if editor_mods.is_dir() else []
		projects.sort(key=lambda p: (p.name not in REFERENCE_PROJECTS, REFERENCE_PROJECTS.index(p.name) if p.name in REFERENCE_PROJECTS else 0, p.name))

		for project in projects:
			for file in (project / 'Stats').rglob('*.stats'):
				fname = file.stem
				try:
					self.data = self.readxml(str(file))
					builder = self.data['stats']['stat_objects']['stat_object']
					if not isinstance(builder, list):
						builder = [builder]
					for node in builder:
						uuid = ''
						name = ''
						fields = node['fields']['field']
						for subnode in fields if isinstance(fields, list) else [fields]:
							if subnode['@name'] == 'Name':
								# Spells are exported with their type as prefix
								name = f'{fname}_{subnode["@value"]}' if fname in SPELL_TYPES else subnode['@value']
							if subnode['@name'] == 'UUID':
								uuid = subnode['@value']
							if name != '' and uuid != '':
								if self.auxdb.get(name, '') == '':
									self.auxdb[name] = uuid
								break
				except Exception as e:
					pass

		print(f'Compiling Auxiliary DB Completed\n')
		with open(self.root_path / 'auxdb.json', 'w', encoding='utf-8') as f:
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
	# usage: py -m helpers.CompileDB "<path to Baldurs Gate 3>"
	cdb = CompileDB(sys.argv[1] if len(sys.argv) > 1 else None)
	cdb.compile()
