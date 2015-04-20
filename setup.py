"""Setup script for the ralint package."""
from setuptools import setup


def get_version():
    """Read the version string from ralint.py."""
    with open('ralint.py') as ralint_file:
        for line in ralint_file:
            if line.startswith('__version__'):
                return eval(line.split('=')[-1])

setup(name='ralint',
      version=get_version(),
      description="Linter for Rally",
      url="http://github.com/wbenroy/ralint",
      author="Ben Roy",
      author_email="wbenroy@gmail.com",
      license="MIT",
      install_requires=[
          'pyral',
          'requests',
          'argparse'
      ],
      py_modules=["ralint"],
      zip_safe=False,
      entry_points={
          'console_scripts': [
              'ralint = ralint:ralint',
          ],
      },
      test_suite='nose.collector',
      tests_require=['nose', 'unittest2'])
