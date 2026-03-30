import importlib.util, pathlib

spec = importlib.util.spec_from_file_location('m', 'src/main-v7-final-working.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

print('Total sites defined:', len(m.SITES))
print('Names:', ', '.join(m.SITES.keys()))
