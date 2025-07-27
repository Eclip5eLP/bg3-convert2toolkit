import argparse
import json
from pathlib import Path

from core.ConvertAPI import ConvertAPI
from core.ConvertCLI import ConvertCLI
from core.ConvertGUI import ConvertGUI
from helpers.LSLibUtil import LSLibUtil

# Main entry for converter script or exe
if __name__ == "__main__":
	# Load Settings
	with open('settings.json', encoding="utf-8") as f:
		settings = json.load(f)
		bg3path = settings.get('bg3path', '')
		compileAux = settings.get('compileAux', 1)
		cli_mode = settings.get('cliMode', True)

	# Handle command line args
	parser = argparse.ArgumentParser(
		prog='Convert2Toolkit',
		description="Used to convert generated Baldur's Gate 3 mod data files into Toolkit versions",
	)
	group = parser.add_mutually_exclusive_group()
	group.add_argument(
		'--cli',
		action='store_true',
		help='force cli mode (overrides settings.json). cannot be used with --gui'
	)
	group.add_argument(
		'--gui',
		action='store_true',
		help='force gui mode (overrides settings.json). cannot be used with --cli'
	)
	parser.add_argument(
		'--compileAux',
		action='store_true',
		help='Compile additional UUIDs from Editor projects'
	)

	args = vars(parser.parse_args())
	if args['cli']:
		cli_mode = True
	elif args['gui']:
		cli_mode = False

	if args['compileAux']:
		compileAux = True

	# Set up paths for file references (needed due to exe packing)
	path_to_root = Path('.').resolve()
	lib_path = Path(__file__).parent.resolve()
	path_to_templates = lib_path / 'lib/templates'
	path_to_lslib = lib_path / 'lib/LSLib'
	path_to_resources = lib_path / 'lib/res'

	# helper for functions from LSLib
	lslib_util = LSLibUtil(path_to_lslib)

	# primary logic for conversion is in api object
	convert_api = ConvertAPI(
		src_bg3_path=bg3path,
		path_to_root=path_to_root,
		path_to_templates=path_to_templates,
		lslib_util=lslib_util,
		compile_aux_db=compileAux
	)

	# Determine process command line vs GUI
	if cli_mode:
		ConvertCLI(convert_api, path_to_root).run()
	else:
		ConvertGUI(convert_api, path_to_root, path_to_resources).run()
