from pathlib import Path
from colorama import Fore
import os


class FixLocale():
	def fix(self, file, conv):
		try:
			data = conv.readxml(file)
			content_list = data.get("contentList") if isinstance(data, dict) else None
			if not isinstance(content_list, dict) or content_list.get("content") is None:
				return False  # not a localization file

			dupes = 0
			vfix = 0
			db = {}
			construct = []

			# Single entries are not parsed as list
			contents = content_list["content"]
			if not isinstance(contents, list):
				contents = [contents]

			# Fix dupes (keep the newest version of a string)
			for x in contents:
				uid = x.get('@contentuid')
				if uid not in db:
					construct.append(x)
					db[uid] = len(construct) - 1
					continue
				dupes += 1
				kept = construct[db[uid]]
				if int(x.get('@version', '1') or 1) >= int(kept.get('@version', '1') or 1):
					construct[db[uid]] = x

			# Set Versions all to 1 so every handle reference works
			for x in construct:
				if x.get('@version', '1') != '1':
					vfix += 1
				x['@version'] = '1'

			data["contentList"]["content"] = construct
			out = Path(str(file)[:-len('.xml')] + '_fix.xml')
			conv.writexml(data, str(out))
			print(f'{Fore.GREEN}[locale] Fixed {os.path.basename(file)} (Duplicates: {dupes}; Version Resets: {vfix}){Fore.RESET}')
			return True
		except Exception as e:
			print(f'{Fore.YELLOW}[locale] Could not review {os.path.basename(file)}: {e}{Fore.RESET}')
			return False
