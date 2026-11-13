#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a separate, test-only APK from the real release APK's support assets."""
import argparse,os,subprocess,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--jdk',type=Path,required=True);p.add_argument('--apk',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--abi',choices=['x86','armeabi-v7a'],default='x86');a=p.parse_args()
src=Path(__file__).resolve().parent;o=a.out.resolve();o.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,JAVA_HOME=str(a.jdk),PATH=str(a.jdk/'bin')+':'+os.environ['PATH'])
def run(*cmd):subprocess.run([str(x) for x in cmd],check=True,env=env)
bt=a.sdk/'build-tools/35.0.0';jar=a.sdk/'platforms/android-36/android.jar'
(o/'AndroidManifest.xml').write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.hypcade.assetbench"><uses-sdk android:minSdkVersion="25" android:targetSdkVersion="28"/><application android:label="Asset benchmark" android:debuggable="true" android:extractNativeLibs="true"><activity android:name=".Main" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>')
(o/'classes').mkdir(exist_ok=True);(o/'dex').mkdir(exist_ok=True)
run(a.jdk/'bin/javac','-source','8','-target','8','-classpath',jar,'-d',o/'classes',src/'Main.java')
run(bt/'d8','--lib',jar,'--min-api','25','--output',o/'dex',*sorted((o/'classes').rglob('*.class')))
compiler=a.sdk/'ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin'/('i686-linux-android25-clang++' if a.abi=='x86' else 'armv7a-linux-androideabi25-clang++')
run(compiler,'-std=c++17','-O3','-shared','-fPIC','-static-libstdc++',src/'bench.cpp','-landroid','-o',o/'libassetbench.so')
run(bt/'aapt','package','-f','-M',o/'AndroidManifest.xml','-I',jar,'-F',o/'unsigned.apk')
with zipfile.ZipFile(a.apk) as source,zipfile.ZipFile(o/'unsigned.apk','a') as dest:
 entries=[i for i in source.infolist() if i.filename.startswith('assets/hypseus/') and not i.is_dir()]
 for i in entries:dest.writestr(i,source.read(i))
 dest.writestr('assets/asset-list.txt','\n'.join(i.filename[7:] for i in entries)+'\n')
 dest.write(o/'dex/classes.dex','classes.dex',compress_type=zipfile.ZIP_DEFLATED)
 dest.write(o/'libassetbench.so','lib/'+a.abi+'/libassetbench.so',compress_type=zipfile.ZIP_DEFLATED)
run(bt/'zipalign','-f','4',o/'unsigned.apk',o/'aligned.apk')
if not (o/'test.keystore').exists():run(a.jdk/'bin/keytool','-genkeypair','-keystore',o/'test.keystore','-storepass','benchmark','-keypass','benchmark','-alias','test','-dname','CN=Local benchmark only','-keyalg','RSA','-validity','30')
run(bt/'apksigner','sign','--ks',o/'test.keystore','--ks-pass','pass:benchmark','--out',o/'benchmark.apk',o/'aligned.apk')
print(o/'benchmark.apk')
