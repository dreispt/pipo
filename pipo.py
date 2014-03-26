#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
pipo is a pip wrapper and utility belt to handle OpenERP installations
It extends pip, providing all it's functions plus the following:

    setup       generate the setpup.py file
    build       generate and run setup.py to create source dist
"""
# from __future__ import unicode_literals
from __future__ import print_function
import argparse
import os
import shutil
import subprocess
import setuptools
from StringIO import StringIO
from pprint import pprint


SETUP_PY = """\
#! /usr/bin/env python
# -*- coding: utf-8 -*-
import setuptools
setup_data = %s
setuptools.setup(**setup_data)
"""


def subprocess_call(cmd, path=None):
    """
    Runs a shell command and returns it's stdout output.
    If a path is given, changes to that directory beforehand.
    """
    if path:
        init_path = os.path.abspath(os.getcwd())
        os.chdir(path)
    # out = subprocess.call(command.split(' '))
    p = subprocess.Popen(
        cmd.split(' '),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    out, err = p.communicate()
    if path:
        os.chdir(init_path)
    if err:
        print("ERROR: %s" % err)
    return out


def get_new_revno(path, vcs):
    """
    Get VCS revision number for a path.
    Supports bzr, hg and git.
     """
    if vcs == 'hg':
        cmd = "hg log --limit 1 --template {rev}"  # + path
    elif vcs == 'git':
        cmd = "git log -1 --oneline --format=format:%at"
    else:
        cmd = 'bzr log --limit=1 --line ./'  # + path

    out = subprocess_call(cmd, path)
    revno = out.strip().split(':')[0]
    return revno or 0


def pretty_format(obj):
    """
    Return a pretty-printed string representation of an object
    """
    f = StringIO()
    pprint(obj, f)
    res = f.getvalue()
    f.close()
    return res


##########
# info file handling
##########

_info_filename = '.pipo-info'


def write_info(path, module_revno, repo_revno):
    info = {
        'module_revno': module_revno,
        'repo_revno': repo_revno,
    }
    open(os.path.join(path, _info_filename), 'w').write(
        pretty_format(info))


def read_info(path):
    # TODO: use some for of safe eval
    res = {}
    info_path = os.path.join(path, _info_filename)
    if os.path.exists(info_path):
        res = eval(open(info_path).read())
    return res or {}


##########


def pull_repo(path, vcs):
    """
    Pull (update) vcs controlled repository.
    Returns the subprocess exit code.
    """
    if os.path.exists(path):
        print("==== Pulling %s %s ====" % (vcs, path))
        initial_cwd = os.path.abspath(os.getcwd())
        params = [vcs, 'pull']
        os.chdir(path)
        res = subprocess.call(params)
        os.chdir(initial_cwd)
        return res


def vcs_detect(path):
    """
    Check the vcs for a path, if it's a repo root.
    """
    vcs_dirs = ['.bzr', '.git', '.hg']
    vcss = [x[1:] for x in os.listdir(path) if x in vcs_dirs]
    return vcss and vcss[0]


def get_path_modules(path, pull=False, repo_vcs=None, repo_revno=None):
    """
    Discover all OpenERP modules under a path.
    Returns a list of tuples (path-to-module, module-name, vcs, repo-revno)
    """
    # Handle only directories
    if not os.path.isdir(path):
        return []
    # Avoid problems with paths ending with '/'
    if not os.path.split(path)[1]:
        path = os.path.split(path)[0]
    # Check if this is the root of a vcs repo
    vcs = vcs_detect(path)
    if vcs:
        if pull:
            pull_repo(path, vcs)
        repo_revno = get_new_revno(path, vcs)
        repo_vcs = vcs

    res = []
    if ('__openerp__.py' in os.listdir(path)
            or os.path.basename(path) == 'server'):
        res = [os.path.split(path) + (repo_vcs, repo_revno)]
    else:
        subdirs = [
            os.path.join(path, x) for x in sorted(os.listdir(path))
            if not(x.startswith('.') or '_unported_' in x)]
        for d in subdirs:
            res.extend(get_path_modules(
                d, pull=pull, repo_vcs=repo_vcs, repo_revno=repo_revno))
    return res


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


def _get_pkgname(name):
    return ('openerp-' + name).replace('_', '-')


def _get_modname(path):
    return (os.path.basename(path) or
            os.path.basename(os.path.dirname(path)))


def setup(mod_dir, revno=None, series='7.0', force=True, cli=False):
    """\
    Add the setup.py file to an OpenERP module.
    """
    # Check directory exists
    if not os.path.isdir(mod_dir):
        if cli:
            print("ERROR: Invalid directory")
        return False

    if os.path.islink(mod_dir):
        if cli:
            print("Ignore (symbolic link)")
        return False

    # module name
    mod_name = _get_modname(mod_dir)
    mod_dotpath = "openerp.addons." + mod_name
    if cli:
        print("* Generating setup.py for %s" % mod_dotpath)

    # prepare data for setuptools
    packages = ([mod_dotpath] +
                [mod_dotpath + '.%s' % x
                 for x in setuptools.find_packages('.')])
    package_data = get_package_data(mod_dir)

    # TODO: use safe eval
    manif = eval(open(os.path.join(mod_dir, '__openerp__.py')).read())
    if not manif.get('installable', True):
        return False  # "not installable."

    manif_depends = [_get_pkgname(x) for x in manif.get('depends')]
    if 'python' in manif.get('external_dependencies', {}):
        manif_depends.extend(manif['external_dependencies']['python'])

    setup_data = {
        'name': _get_pkgname(mod_name),
        'version': series + '.' + str(revno),
        'description': manif.get('name'),
        'long_description': manif.get('description'),
        'url': manif.get('website') or 'http://openerpapps.info',
        'author': manif.get('author', 'Unknown'),
        'author_email': 'info@openerp.com',
        'license': manif.get('license', 'AGPL-3'),
        'package_dir': {mod_dotpath: "."},
        'packages': packages,
        'package_data': {'openerp.addons.' + mod_name: package_data},
        'install_requires': manif_depends, }

    setup_data_text = pretty_format(setup_data)
    with open(os.path.join(mod_dir, 'setup.py'), 'w') as f:
        f.write(SETUP_PY % (setup_data_text))

    # Create README avoiding build warnings
    readme = manif.get('description', '')  # .encode('UTF-8')
    open(os.path.join(mod_dir, 'README.rst'), 'w').write(readme)
    # Build Manifest
    open(os.path.join(mod_dir, 'MANIFEST.in'), 'w').write(
        get_manifest_lines(mod_dir))
    return True


def build(path, dist_dir, force=False, pull=False, cli=False):
    """
    Discover all OpenERP modules under a directory, build their packages and
    place them in a distribution directory.
    """
    dist_dir = dist_dir and os.path.abspath(dist_dir)
    if cli:
        print("\n--------")
        print("Building!")
        print("* Target dir is %s" % os.path.abspath(path))
        print("* Dist dir is %s" % dist_dir)
        print("--------")

    modules = get_path_modules(path, pull=pull)
    for dirname, module, vcs, repo_revno in modules:
        if cli:
            print("* %s %s %s" % (vcs, dirname, module), end=" ")
        # Generate setup.py
        mod_dir = os.path.join(dirname, module)
        mod_info = read_info(mod_dir)

        last_repo_revno = mod_info.get('repo_revno', 0)
        if not force and last_repo_revno == repo_revno:
            # print("repo unchanged")
            print(".")
            continue

        revno = get_new_revno(mod_dir, vcs)
        last_revno = mod_info.get('module_revno')
        if last_revno and last_revno == revno and not force:
            # print("module unchanged")
            print(".")
            continue

        if '__openerp__.py' in os.listdir(mod_dir):
            installable = setup(mod_dir, revno=revno, cli=False)
            if not force and not installable:
                # print("not installable")
                print(".")
                continue

        try:
            subprocess_call('python setup.py --quiet sdist', mod_dir)
            write_info(mod_dir, revno, repo_revno)
        except:
            pass
        # Move distribution to final location
        if dist_dir:
            for x in os.listdir(os.path.join(mod_dir, 'dist')):
                print("BUILT %s" % x)
                shutil.move(
                    os.path.join(mod_dir, 'dist', x),
                    os.path.join(dist_dir, x))


def create(name):
    subprocess_call('virtualenv --system-site-packages %s' % name)
    subprocess_call('createdb %s' % name)


def pip(command, *args):
    cmd = ['pip', command]
    if command in ['install', 'search']:
        extra = ['http://openerpapps.info/simple/openerp/7.0']
        cmd.extend(['--extra-index-url', ','.join(extra)])
    cmd.extend(list(args[0]))
    subprocess_call(' '.join(cmd))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subparser_name")

    parser_setup = subparsers.add_parser("setup")
    parser_setup.add_argument("mod_dir", help="Module directory")

    parser_build = subparsers.add_parser("build")
    parser_build.add_argument("path", help="Path to discover modules")
    parser_build.add_argument("dist_dir", help="Directory for built packages")
    parser_build.add_argument(
        "-f", "--force", action="store_true",
        help="Force build even if module has no changes")
    parser_build.add_argument(
        "-p", "--pull", action="store_true",
        help="Pull changes from remote VCS repositories")

    args = parser.parse_args()
    if args.subparser_name == "setup":
        setup(args.mod_dir, cli=True)
    elif args.subparser_name == "build":
        build(
            args.path,
            args.dist_dir,
            force=args.force,
            pull=args.pull,
            cli=True)
    else:
        print("Invalid command.")
