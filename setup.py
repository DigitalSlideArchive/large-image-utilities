import os

from setuptools import setup

with open('README.rst') as fh:
    readme = fh.read()

description = 'Experimental utilities for Large Image.'
long_description = readme


def prerelease_local_scheme(version):
    """
    Return local scheme version unless building on master in CircleCI.

    This function returns the local scheme version number
    (e.g. 0.0.0.dev<N>+g<HASH>) unless building on CircleCI for a
    pre-release in which case it ignores the hash and produces a
    PEP440 compliant pre-release version number (e.g. 0.0.0.dev<N>).
    """
    from setuptools_scm.version import get_local_node_and_date

    if os.getenv('CIRCLE_BRANCH') in ('master', ):
        return ''
    else:
        return get_local_node_and_date(version)


try:
    from setuptools_scm import get_version

    version = get_version(local_scheme=prerelease_local_scheme)
except (ImportError, LookupError):
    pass

setup(
    name='large-image-utilities-experimental',
    use_scm_version={'local_scheme': prerelease_local_scheme,
                     'fallback_version': 'development'},
    setup_requires=['setuptools-scm'],
    description=description,
    long_description=long_description,
    license='Apache Software License 2.0',
    author='Kitware Inc',
    author_email='kitware@kitware.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Scientific/Engineering',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    install_requires=[
        'girder-client',
        'large-image',
        'tifftools',
    ],
    extras_require={
        'sources': [
            'large-image[sources]',
        ],
    },
    py_modules=['ttdump_to_tiff', 'lisource_compare', 'li_summary', 'copy_annotations'],
    entry_points={
        'console_scripts': [
            'ttdump_to_tiff = ttdump_to_tiff:command',
            'lisource_compare = lisource_compare:command',
            'li_summary = li_summary:command',
            'copy_annotations = copy_annotations:command',
        ]
    },
    python_requires='>=3.6',
)
