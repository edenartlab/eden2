from setuptools import setup, find_packages

setup(
    name='eden',
    version='0.1.1',
    packages=find_packages(),
    install_requires=[
        'requests>=2.25.1'
    ],
    author='Eden.art',
    author_email='gene@eden.art',
    description='Client library Eden',
    url='https://github.com/edenartlab/eden2',
)
