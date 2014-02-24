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
    revno = out.strip().split(':')[0]
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


#def _is_module(mod_dir):
#    if os.path.isdir(mod_dir):
#        if os.path.exists(join(mod_dir, '__openerp__.py')):
#            return True
#    return False


def _list_modules(parent_path):
    res = []
    if os.path.isdir(parent_path):
        if os.path.exists(join(parent_path, '__openerp__.py')):
            return [parent_path]
        # else:
        for root, dirs, files in os.walk(parent_path):
            for x in dirs:
                curdir = join(root, x)
                if os.path.exists(join(curdir, '__openerp__.py')):
                    res.append(curdir)
    return res


def setup(mod_dir, series='7.0', force=True, cli=False):
    try:
        import setuptools
    except ImportError:
        print "\nERROR: setuptools not available. You should 'pip install setuptools'."
        return False

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

    mod_dir = os.path.abspath(mod_dir)
    os.chdir(mod_dir)

    # Check vcs revision number
    # Unless forced, exit if revision number hasn't changed
    revno = get_revno(mod_dir)
    if not force:
        try:
            revno_file = os.path.join(mod_dir, 'revno.txt')
            old_revno = open(revno_file, 'r').read()
            print mod_dir, old_revno, '->', revno
            if revno == old_revno:
                return False  # "no changes."
        except IOError:
            pass
    open('revno.txt', 'w').write(revno)

    # prepare data for setuptoolsy
    packages = ([mod_dotpath] +
                [mod_dotpath + '.%s' % x
                 for x in setuptools.find_packages('.')])
    package_data = get_package_data(mod_dir)

    # TODO: use safe eval
    manif = eval(open(join(mod_dir, '__openerp__.py')).read())
    if not manif.get('installable', True):
        return False  # "not installable."
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
    #os.chdir(cwd)
    return True


def build(path, dist_dir, force=False, cli=False):
    import subprocess
    import shutil

    dist_dir = dist_dir and os.path.abspath(dist_dir)
    if cli:
        print "\nBuilding!"
        print "* Target dir is ", os.path.abspath(path)
        print "* Dist dir is ", dist_dir
    for mod_dir in sorted(_list_modules(os.path.abspath(path))):
        if cli:
            print "* %s" % (os.path.dirname(mod_dir)),
        # Generate setup.py
        if setup(mod_dir, force=force, cli=False):
            # Call setup.py
            os.chdir(mod_dir)
            subprocess.call(['python', 'setup.py', '--quiet', 'sdist'])
            # Move distribution to final location
            if dist_dir:
                for x in os.listdir(join(mod_dir, 'dist')):
                    shutil.move(join(mod_dir, 'dist', x), join(dist_dir, x))
        else:
            print "."
    # print 'DONE.'


def _run_shell(cmd):
    from subprocess import Popen, PIPE
    print ' '.join(cmd)
    p = Popen(cmd)
    p.communicate()


def create(name):
    from subprocess import Popen, PIPE
    _run_shell(['virtualenv', '--system-site-packages', name])
    _run_shell(['createdb', name])


def pip(command, *args):
    cmd = ['pip', command]
    if command in ['install', 'search']:
        extra = ['http://openerpapps.info/simple/openerp/7.0']
        cmd.extend(['--extra-index-url', ','.join(extra)])
    cmd.extend(list(args[0]))
    _run_shell(cmd)


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
            force = len(params) > 2 and params[2] == '--force' or None
            if force:
                print "FORCE"
            build(module_dir, dist_dir, force=force, cli=True)

        elif command == 'create':
            create(params[0])

        else:
            pip(command, params)
