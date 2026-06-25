from setuptools import setup

APP = ['server.py']
DATA_FILES = [('', ['index.html'])]
OPTIONS = {
    'argv_emulation': False,
    'packages': [],
    'includes': [],
    'excludes': ['tkinter', 'test', 'unittest', 'pydoc'],
    'iconfile': 'app_logo.icns',
    'plist': {
        'CFBundleName': 'To Do',
        'CFBundleDisplayName': 'To Do',
        'CFBundleIdentifier': 'com.todo.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
