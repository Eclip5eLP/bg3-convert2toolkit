from pathlib import Path
import os, re

# Standalone helper: lists ID attributes that aren't a valid 36 character UUID in all files below the working dir
if __name__ == "__main__":
	for f in Path('.').glob('**/*'):
		if not f.is_file() or os.path.basename(f) == 'idchecker.py' or os.path.basename(f).endswith('.lsf'):
			continue
		print(f'- {f}')

		try:
			with open(f, encoding="utf-8-sig") as file:
				data = file.read()
			lst = re.findall(r'\<attribute id\="ID" type="FixedString" value\="*.*" \/\>', data)
			for idd in lst:
				fid = idd.replace('<attribute id="ID" type="FixedString" value="', '').replace('" />', '')
				if len(fid) != 36:
					print(fid)
		except Exception as e:
			continue
