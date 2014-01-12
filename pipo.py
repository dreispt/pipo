#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
pipo is a pip wrapper and utility belt to handle OpenERP installations
It extends pip, providing all it's functions plus the following:

    setup       generate the setpup.py file
    build       generate and run setup.py to create source dist
"""

import os
from os.path import join


def get_revno(module_path='.'):
    """ Get VCS revision for the given path """
    from subprocess import Popen, PIPE
    cmd = 'bzr log --limit=1 --line ' + module_path
    p = Popen(cmd.split(' '), stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    revno = out.decode().strip().split(':')[0]
    return revno


def get_package_data(dir):
    res = []
    for d, dir_list, file_list in os.walk(dir):
        if not d.endswith('.egg-info'):
            exts = []
            for file in file_list:
                ext = os.path.splitext(file)[1]
                if (ext not in
                        ['.py', '.pyc', '.tmp', '.in'] and
                    file not in
                        ['MANIFEST.in', 'revno.txt', 'last-revno.tmp']):
                    x = ext and (d + '/*' + ext) or (d + '/' + file)
                    x = x[len(dir) + 1:]
                    if x not in exts:
                        exts.append(x)
            res.extend(exts)
    return res


def get_manifest_lines(dir):
    exclusions = ['build', 'dist']
    lines = []
    for x in os.listdir(dir):
        if x not in exclusions and not x.endswith('.egg-info'):
            if os.path.isfile(os.path.join(dir, x)):
                lines.append('include %s\n' % x)
            else:
                lines.append('graft %s\n' % x)
    return '\n'.join(lines)


def _pprint(obj):
    """ Return a pretty-printed string representation of an object """
    from StringIO import StringIO
    from pprint import pprint
    f = StringIO()
    pprint(obj, f)
    res = f.getvalue()
    f.close()
    return res


def _get_pkgname(name):
    return ('openerp-' + name).replace('_', '-')


def _get_modname(path):
    return (os.path.basename(path) or
            os.path.basename(os.path.dirname(path)))


def setup(mod_dir, series='7.0', force=True, cli=False):
    try:
        import setuptools
    except ImportError:
        return "ERROR: setuptools not available. You should 'pip install setuptools'."

    # Check directory exists
    if not os.path.isdir(mod_dir):
        if cli:
            print("ERROR: Invalid directory")
        return False

    # module name
    mod_name = _get_modname(mod_dir)
    mod_dotpath = "openerp.addons." + mod_name
    if cli:
        print("* Generating setup.py for %s" % mod_dotpath)

    # Check vcs revision number
    # Unless forced, exit if revision number hasn't changed
    revno = get_revno(mod_dir)
    if not force:
        try:
            revno_file = os.path.join(mod_dir, 'revno.txt')
            old_revno = open(revno_file, 'r').readlines()
            if revno != old_revno:
                return "no changes."
        except OSError:
            pass
    open('revno.txt', 'w').write(revno)

    # prepare data for setuptoolsy
    packages = ([mod_dotpath] +
                [mod_dotpath + '%s.%s' % (mod_name, x)
                 for x in setuptools.find_packages()])
    package_data = get_package_data(mod_dir)

    # TODO: use safe eval
    manif = eval(open(join(mod_dir, '__openerp__.py')).read())
    if not manif.get('installable', True):
        return "not installable."
    setup_data = {
        'name': _get_pkgname(mod_name),
        'version': series + '.' + str(revno),
        'description': manif.get('name'),
        'long_description': manif.get('description'),
        'url': manif.get('website', 'http://openerpapps.info'),
        'author': manif.get('author', 'Unknown'),
        'author_email': 'info@openerp.com',
        'license': manif.get('license', 'AGPL-3'),
        'package_dir': {mod_dotpath: "."},
        'packages': packages,
        'package_data': {'openerp.addons.' + mod_name: package_data},
        'install_requires': [_get_pkgname(x) for x in manif.get('depends')]}

    setup_data_text = _pprint(setup_data)
    with open(os.path.join(mod_dir, 'setup.py'), 'w') as f:
        f.write("""\
#! /usr/bin/env python
# -*- coding: utf-8 -*-
import setuptools
setup_data = %s
setuptools.setup(**setup_data)
""" % (setup_data_text))

    # Create README avoiding build warnings
    open(join(mod_dir, 'README.rst'), 'w').write(manif.get('description', ''))
    # Build Manifest
    open(join(mod_dir, 'MANIFEST.in'), 'w').write(get_manifest_lines(mod_dir))
    return ""


def build(path_glob, dist_dir, force=False, cli=False):
    import glob
    import subprocess
    import shutil

    for mod_dir in sorted(glob.glob(path_glob)):
        if cli:
            print("Building %s" % (mod_dir))

        # Pre-checks
        if not os.path.isdir(mod_dir):
            if cli:
                print("ERROR: not a valid directory.")
            continue
        if not os.path.exists(join(mod_dir, '__openerp__.py')):
            if cli:
                print("ERROR: __openerp__.py not found")
            continue

        # Start
        module = _get_modname(mod_dir)
        print '* %s ...' % module,
        dist_dir = dist_dir and os.path.abspath(dist_dir)

        # Generate setup.py
        setup(mod_dir, cli=False)

        # Call setup.py
        cwd = os.path.abspath(os.getcwd())
        mod_dir = os.path.abspath(mod_dir)
        os.chdir(mod_dir)
        subprocess.call(['python', 'setup.py', '--quiet', 'sdist'])
        os.chdir(cwd)

        # Move distribution to final location
        if dist_dir:
            for x in os.listdir(join(mod_dir, 'dist')):
                shutil.move(join(mod_dir, 'dist', x), join(dist_dir, x))

        print ' DONE.'


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print(__doc__)
    else:
        command = sys.argv[1]
        params = sys.argv[2:]

        if command == 'setup' and params:
            setup(params[0], cli=True)

        elif command == 'build' and params:
            module_dir = params[0]
            dist_dir = len(params) > 1 and params[1] or None
            build(module_dir, dist_dir, cli=True)

        else:
            print("Invalid options. Type 'pipo help' for information")
