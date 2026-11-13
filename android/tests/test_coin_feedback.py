#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
"""Exercise production coin-edge handling with a stub mixer; check licensed PCM asset."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tempfile,wave,zipfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--apk",action="append",default=[])
args=parser.parse_args()
root=Path(__file__).resolve().parents[2]
s=(root/'src/sound/sound.cpp').read_text()
body=s[s.index('void coin_input(unsigned coin, bool down)'):s.index('\n#endif',s.index('void coin_input(unsigned coin, bool down)'))]
code='''#include <cassert>
unsigned g_coin_held=0; bool g_sound_initialized=true,g_bSoundMuted=false,enabled=true;
bool is_enabled(){return enabled;}
unsigned char pcm[2]; struct {unsigned char* pu8Buf; unsigned uLength,uChannels;} g_sample_coin={pcm,2,1};
void *g_audio_device=nullptr; bool locked=false; int plays=0;
bool SDL_LockAudioStream(void*) { assert(!locked);locked=true;return true; }
void SDL_UnlockAudioStream(void*) { assert(locked);locked=false; }
namespace samples { void play(unsigned char* b,unsigned n,unsigned c) {assert(locked && b==pcm && n==2 && c==1);++plays;} }
'''+body+'''
int main(){
coin_input(0,true); assert(plays==1 && !locked);
coin_input(0,true); assert(plays==1); // held/key repeat or duplicate input hook
coin_input(0,false);assert(plays==1);
coin_input(0,true);assert(plays==2);
coin_input(1,true);assert(plays==3); // independent second coin switch
coin_input(2,true);assert(plays==3);
coin_input(0,false);g_bSoundMuted=true;coin_input(0,true);assert(plays==3);
coin_input(0,false);g_bSoundMuted=false;enabled=false;coin_input(0,true);assert(plays==3);
coin_input(0,false);enabled=true;g_sound_initialized=false;coin_input(0,true);assert(plays==3);
coin_input(0,false);g_sound_initialized=true;g_sample_coin.pu8Buf=nullptr;coin_input(0,true);assert(plays==3);
}
'''
with tempfile.TemporaryDirectory(prefix='hypcade-coin-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(code)
 subprocess.run(['c++','-std=c++11',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
asset=root/'sound/hypcade-coin.wav'
with wave.open(str(asset)) as w:
 assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,44100)
 assert 0<w.getnframes()/w.getframerate()<1.5
 assert any(w.readframes(w.getnframes()))
provenance=json.loads((root/'android/audio-sources/coin/provenance.json').read_text())
assert hashlib.sha256(asset.read_bytes()).hexdigest()==provenance['packaged_sha256']
assert provenance['license']=='CC0-1.0'
print('Coin feedback: press/repeat/release, second slot, mute/disabled/uninitialized/missing sample, mixer lock and licensed PCM passed')

for name in args.apk:
 with zipfile.ZipFile(name) as apk:
  assert apk.read("assets/hypseus/sound/hypcade-coin.wav.bin")==asset.read_bytes()
  assert not any(n.startswith("assets/licenses/") for n in apk.namelist())
  notices=(root/"android/artifacts/hypcade-licenses.txt").read_bytes()
  assert b"bassmosphere" in notices and b"CC0 1.0 Universal" in notices
  assert not any("audio-sources" in n for n in apk.namelist())
 print(Path(name).name+": coin sample packaged; notices supplied separately; original source excluded")
