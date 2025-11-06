import importlib

try:
    importlib.import_module('app.main')
    print('IMPORT_OK')
except Exception as exc:
    print('IMPORT_ERROR:', exc)
