#!/usr/bin/env python3
"""
Compress JPEG, PNG and GIF file by jpegtran, optipng
and gifsicle losslessly and respectively in batch mode,
inplace and keep mtime unchanged.

Author:   xinlin-z
Github:   https://github.com/xinlin-z/smally
Blog:     https://CS4096.com
License:  MIT
"""
import platform
if platform.system() == 'Windows':
    raise NotImplementedError('Not yet support Windows!')


import sys
import os
import subprocess
import argparse
import multiprocessing as mp
import shlex


__all__ = ['is_jpeg_progressive',
           'jpegtran',
           'optipng',
           'gifsicle']


def _cmd(cmd: str, shell: bool=False) -> tuple[int,bytes,bytes]:
    """ execute a command w/ or w/o shell,
        return returncode, stdout, stderr """
    p = subprocess.run(cmd if shell else shlex.split(cmd),
                       shell=shell,
                       capture_output=True)
    return p.returncode, p.stdout, p.stderr


def is_jpeg_progressive(pathname: str) -> bool:
    """ check if pathname is progressive jpeg format """
    cmdstr = 'file %s | grep progressive' % pathname
    code, _, _ = _cmd(cmdstr, shell=True)
    return code == 0


def jpegtran(pathname: str) -> tuple[int,int]:
    """ use jpegtran to compress pathname,
        return tuple (saved, orginal_size). """
    try:
        basename = os.path.basename(pathname)
        wd = os.path.dirname(os.path.abspath(pathname))
        # baseline
        file_1 = wd + '/'+ basename + '.smally.baseline'
        cmd_1 = 'jpegtran -copy none -optimize -outfile %s %s'\
                                                        % (file_1, pathname)
        _cmd(cmd_1)
        # progressive
        file_2 = wd + '/' + basename + '.smally.progressive'
        cmd_2 = 'jpegtran -copy none -progressive -optimize -outfile %s %s'\
                                                        % (file_2, pathname)
        _cmd(cmd_2)
        # get jpg type
        progressive = is_jpeg_progressive(pathname)
        # choose the smallest one
        size = os.path.getsize(pathname)
        size_1 = os.path.getsize(file_1)
        size_2 = os.path.getsize(file_2)
        if size <= size_1 and size <= size_2:
            select_file = 0
            if size == size_2 and not progressive:
                select_file = 2  # progressive is preferred
        else:
            select_file = 2 if size_2<=size_1 else 1
        # get mtime
        _, mtime, _ = _cmd('stat -c "%y" ' + pathname)
        # rm & mv
        if select_file == 0:  # origin
            os.remove(file_1)
            os.remove(file_2)
            saved = 0
        elif select_file == 1:  # baseline
            os.remove(pathname)
            os.remove(file_2)
            os.rename(file_1, pathname)
            saved = size_1 - size
        else:  # select_file == 2:  # progressive
            os.remove(pathname)
            os.remove(file_1)
            os.rename(file_2, pathname)
            saved = size_2 - size
        # keep mtime
        if select_file != 0:
            _cmd('touch -m -d "'+mtime.decode()+'" '+pathname)
        return saved, size
    except BaseException:
        try:
            if os.path.exists(pathname):
                try: os.remove(file_1)
                except FileNotFoundError: pass
                try: os.remove(file_2)
                except FileNotFoundError: pass
            else:
                if (os.path.exists(file_1) and
                        os.path.exists(file_2)):
                    if os.path.getsize(file_1) >= os.path.getsize(file_2):
                        os.remove(file_1)
                        os.rename(file_2, pathname)
                    else:
                        os.remove(file_2)
                        os.rename(file_1, pathname)
                elif os.path.exists(file_2):
                    os.rename(file_2, pathname)
                else: os.rename(file_1, pathname)
        except UnboundLocalError:
            pass
        raise


class make_choice:
    """ execute command, compare size, and make choice """

    def __init__(self, cmdstr: str) -> None:
        self.cmdstr = cmdstr

    def __call__(self, pathname: str) ->tuple[int,int]:
        try:
            basename = os.path.basename(pathname)
            wd = os.path.dirname(os.path.abspath(pathname))
            tmpfile = wd + '/' + basename + '.smally'
            cmds = self.cmdstr % (pathname,tmpfile)
            _cmd(cmds)
            size_1 = os.path.getsize(pathname)
            size_2 = os.path.getsize(tmpfile)
            if size_1 == size_2:
                os.remove(tmpfile)
                saved = 0
            else:
                saved = size_2 - size_1
                _, mtime, _ = _cmd('stat -c "%y" ' + pathname)
                os.remove(pathname)
                os.rename(tmpfile, pathname)
                _cmd('touch -m -d "'+mtime.decode()+'" '+pathname)
            return saved, size_1
        except BaseException:
            try:
                if os.path.exists(pathname):
                    os.remove(tmpfile)
                elif os.path.exists(tmpfile):
                    os.rename(tmpfile, pathname)
            except FileNotFoundError:
                pass
            raise


# must have two %s
optipng = make_choice('optipng -fix -o7 -zm1-9 %s -out %s')
gifsicle = make_choice('gifsicle -O3 --colors 256 %s -o %s')


def _show(ftype: str, pathname: str, saved: tuple[int,int]) -> None:
    if saved[0] == 0:
        logstr = '--'
    else:
        logstr = str(saved[0]) +' '+ str(round(saved[0]/saved[1]*100,2)) +'%'
    tail = '' if ftype!='j' else \
                  '[p]' if is_jpeg_progressive(pathname) else '[b]'
    print(' '.join((pathname, logstr, tail)))


def _find_xargs(pnum: int, ftype: str='', recur: bool=False) -> None:
    pnum = min(mp.cpu_count(), pnum)
    print('# parallel process number: ', pnum)
    cmdstr = 'find -L %s -type f -print0 %s | ' \
             'xargs -P%d -I+ -0 python %s %s +' \
             % (args.pathname,
                '' if recur else '-maxdepth 1',
                pnum,
                sys.argv[0],
                ftype)
    try:
        p = subprocess.Popen(cmdstr, shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        for line in iter(p.stdout.readline, b''):  # type: ignore
            print(line.decode(), end='')
    except Exception as e:
        print(repr(e))
        sys.exit(3)  # subprocess error


_VER = 'smally V0.54 by xinlin-z \
        (https://github.com/xinlin-z/smally)'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-V', '--version', action='version', version=_VER)
    parser.add_argument('-j', '--jpegtran', action='store_true',
                        help='use jpegtran to compress jpeg file')
    parser.add_argument('-p', '--optipng', action='store_true',
                        help='use optipng to compress png file')
    parser.add_argument('-g', '--gifsicle', action='store_true',
                        help='use gifsicle to compress gif file')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='recursively working on subdirectories ')
    parser.add_argument('pathname', help='specify the pathname, '
                                         'file or directory')
    parser.add_argument('-P',
                        type=int,
                        default=mp.cpu_count(),
                        metavar='',
                        help='number of parallel processes, '
                             'default is the logical cpu number')
    args = parser.parse_args()

    # get pathname type
    # pathname might contains unusual chars, here is test
    cmdstr = "file %s | awk '{print $2}'" % args.pathname
    rcode, stdout, stderr = _cmd(cmdstr, shell=True)
    if rcode != 0:
        print('# error occure while executing: file %s' % args.pathname)
        print(stderr.decode(), end='')
        sys.exit(rcode)
    pathname_type = stdout.decode().strip()
    if pathname_type not in ('JPEG','PNG','GIF','directory'):
        print(f'# pathname type of {args.pathname} is not supported')
        sys.exit(2)  # file type not in range

    # if type specified
    if any((args.jpegtran,args.optipng,args.gifsicle)):
        if args.jpegtran and pathname_type=='JPEG':
            _show('j', args.pathname, jpegtran(args.pathname))
        elif args.optipng and pathname_type=='PNG':
            _show('p', args.pathname, optipng(args.pathname))
        elif args.gifsicle and pathname_type=='GIF':
            _show('g', args.pathname, gifsicle(args.pathname))
        elif pathname_type == 'directory':
            ftype = ''
            ftype += ' -j' if args.jpegtran else ''
            ftype += ' -p' if args.optipng else ''
            ftype += ' -g' if args.gifsicle else ''
            _find_xargs(args.P, ftype, args.recursive)
        else:
            sys.exit(1)  # file type not match
        sys.exit(0)

    # no type specified
    if pathname_type == 'JPEG':
        _show('j', args.pathname, jpegtran(args.pathname))
    elif pathname_type == 'PNG':
        _show('p', args.pathname, optipng(args.pathname))
    elif pathname_type == 'GIF':
        _show('g', args.pathname, gifsicle(args.pathname))
    elif pathname_type == 'directory':
        _find_xargs(args.P, '', args.recursive)
    sys.exit(0)

