#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile host ROM checks for Android and run them in an isolated device folder."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
from threading import Lock

import moves as move_tools


def compile_android(source, output, flags=()):
    sdk=Path(os.environ.get('ANDROID_HOME',Path.home()/'Android/Sdk'))
    cc=sdk/'ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/i686-linux-android25-clang'
    src=move_tools.ROOT/'vendor/src'
    subprocess.run([str(cc),'-O3','-ffp-contract=off','-std=c11','-D_POSIX_C_SOURCE=200809L',
        '-Wall','-Wextra','-Werror',*flags,'-I'+str(src),str(source),
        *[str(src/name) for name in move_tools.SOURCES],'-lz','-lm','-o',str(output)],check=True)
    return output


class AndroidRunner:
    def __init__(self, serial, folder, binaries):
        self.adb=['adb','-s',serial]
        self.abi=subprocess.check_output(self.adb+['shell','getprop','ro.product.cpu.abi'],text=True).strip()
        if self.abi!='x86':raise ValueError('The Android check currently requires an x86 emulator')
        self.sdk=subprocess.check_output(self.adb+['shell','getprop','ro.build.version.sdk'],text=True).strip()
        self.remote='/data/local/tmp/hypcade-rom-check-'+hashlib.sha256(str(folder).encode()).hexdigest()[:12]
        self.files={};self.lock=Lock()
        subprocess.run(self.adb+['shell','mkdir','-p',self.remote],check=True)
        for binary in binaries:
            remote=self.put(Path(binary))
            subprocess.run(self.adb+['shell','chmod','755',remote],check=True)

    def destination(self,path):
        return self.remote+'/'+hashlib.sha256(str(path).encode()).hexdigest()[:20]+path.suffix

    def put(self,path):
        path=path.resolve();remote=self.destination(path)
        with self.lock:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if self.files.get(path)!=digest:
                subprocess.run(self.adb+['push',str(path),remote],check=True,stdout=subprocess.DEVNULL)
                self.files[path]=digest
        return remote

    def run(self, command, **kwargs):
        converted=[];outputs=[]
        for index,arg in enumerate(command):
            p=Path(arg)
            if p.is_absolute():
                if p.is_file():converted.append(self.put(p))
                else:
                    converted.append(self.destination(p));outputs.append((p,self.destination(p)))
            else:converted.append(str(arg))
        result=subprocess.run(self.adb+['shell',shlex.join(converted)],**kwargs)
        if result.returncode==0:
            for local,remote in outputs:
                subprocess.run(self.adb+['pull',remote,str(local)],check=True,stdout=subprocess.DEVNULL)
        return result
