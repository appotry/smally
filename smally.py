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
import sqlite3


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


class mtt:
    """ mtime tools class """

    @staticmethod
    def get(pathname: str) -> bytes:
        _, mtime, _ = _cmd('stat -c "%y" ' + pathname)
        return mtime.strip()

    @staticmethod
    def set(pathname: str, mtime: bytes) -> None:
        _cmd('touch -m -d "'+mtime.decode()+'" '+pathname)


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
        mtime = mtt.get(pathname)
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
            mtt.set(pathname, mtime)
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
                mtime = mtt.get(pathname)
                os.remove(pathname)
                os.rename(tmpfile, pathname)
                mtt.set(pathname, mtime)
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
    tail = '' if ftype!='JPEG' else \
                  '[p]' if is_jpeg_progressive(pathname) else '[b]'
    print(' '.join((pathname, logstr, tail)))


def _find_xargs(pnum: int, pathname: str,
                ftype: str='', recur: bool=False) -> None:
    pnum = min(mp.cpu_count(), pnum)
    print('# parallel process number: ', pnum)
    cmdstr = 'find -L %s -type f -print0 %s | ' \
             'xargs -P%d -I+ -0 python %s %s +' \
             % (pathname,
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


# There is a SQLite database file for every folder to prevent from re-doing.
TNAME = 'filescan'
FDBNAME = '.smally.db'
CREATE_SQL = f"""
create table {TNAME}(
    id integer primary key,
    fname text not null unique,  -- file basename, include suffix
    bsize int,                   -- byte size
    mtime blob                   -- mtime
);
"""


class operate_db:

    def __init__(self, pathname: str) -> None:
        self.basename = os.path.basename(pathname)
        self.bsize = os.path.getsize(pathname)
        self.wd = os.path.dirname(os.path.abspath(pathname))
        self.dbfile = self.wd + '/' + FDBNAME
        self.id = None
        self.mtime = mtt.get(pathname)
        self._detect_create_table()

    def _detect_create_table(self) -> None:
        conn = sqlite3.connect(self.dbfile)
        cur = conn.cursor()
        sql = f'select * from sqlite_master where type="table"'\
              f' and name="{TNAME}"'
        if cur.execute(sql).fetchone() is None:
            cur.execute(CREATE_SQL)
            conn.commit()
        conn.close()

    def need_compress(self) -> bool:
        conn = sqlite3.connect(self.dbfile)
        cur = conn.cursor()
        sql = f'select id, bsize, mtime from {TNAME}'\
              f' where fname="{self.basename}"'
        result = cur.execute(sql).fetchone()
        conn.close()
        if not result:
            return True
        self.id = result[0]
        if self.bsize>result[1] or self.mtime!=result[2]:
            return True
        return False

    def update(self, bsize: int) -> None:
        conn = sqlite3.connect(self.dbfile)
        cur = conn.cursor()
        if self.id:
            sql = f'update {TNAME} set bsize=?,mtime=? where id={self.id}'
            cur.execute(sql, (bsize,self.mtime))
        else:
            sql = f'insert into {TNAME}(fname,bsize,mtime) values(?,?,?)'
            cur.execute(sql, (self.basename,bsize,self.mtime))
        conn.commit()
        conn.close()


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
        sys.exit(2)  # file type not in range

    if not any((args.jpegtran,args.optipng,args.gifsicle)):
        args.jpegtran = args.optipng = args.gifsicle = 1

    if args.jpegtran and pathname_type=='JPEG':
        doer = jpegtran
    elif args.optipng and pathname_type=='PNG':
        doer = optipng
    elif args.gifsicle and pathname_type=='GIF':
        doer = gifsicle
    elif pathname_type == 'directory':
        ftype = ''
        ftype += ' -j' if args.jpegtran else ''
        ftype += ' -p' if args.optipng else ''
        ftype += ' -g' if args.gifsicle else ''
        _find_xargs(args.P, args.pathname, ftype, args.recursive)
        sys.exit(0)
    else:
        sys.exit(1)  # file type not match

    db = operate_db(args.pathname)
    if db.need_compress():
        sizes = doer(args.pathname)
        db.update(sizes[1]+sizes[0])  # saved is negative!
        _show(pathname_type, args.pathname, sizes)

    sys.exit(0)


