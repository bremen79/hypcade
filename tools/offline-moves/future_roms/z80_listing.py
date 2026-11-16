#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostic Z80 listings for ROM investigation; not a semantic proof engine."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

# Local analysis helper; opcode structure checked against the bundled Z80 core.
R=['B','C','D','E','H','L','(HL)','A'];CC=['NZ','Z','NC','C','PO','PE','P','M']
def ins(data,start):
 p=start;idx=None
 def byte():
  nonlocal p
  v=data[p];p+=1;return v
 def word():return byte()|byte()<<8
 def hx(n):return '%04X'%n
 op=byte()
 while op in (0xdd,0xfd):idx='IX' if op==0xdd else 'IY';op=byte()
 hl=idx or 'HL';rp=['BC','DE',hl,'SP'];rp2=rp[:3]+['AF'];disp=None
 def reg(i):
  nonlocal disp
  if i==6 and idx:
   if disp is None:
    d=byte();disp=d if d<128 else d-256
   return '(%s%+d)'%(idx,disp)
  if idx and i in (4,5):return idx+('H' if i==4 else 'L')
  return R[i]
 x,y,z=op>>6,(op>>3)&7,op&7;q=y&1;a=y>>1
 if op==0xcb:
  mem=reg(6) if idx else None;o=byte();xx,yy,zz=o>>6,(o>>3)&7,o&7
  r=mem or R[zz];t=('%s %s'%(['RLC','RRC','RL','RR','SLA','SRA','SLL','SRL'][yy],r)) if xx==0 else '%s %d,%s'%(['','BIT','RES','SET'][xx],yy,r)
 elif op==0xed:
  o=byte();xx,yy,zz=o>>6,(o>>3)&7,o&7;pp=yy>>1;qq=yy&1
  if xx==1:
   if zz==0:t='IN %s,(C)'%R[yy]
   elif zz==1:t='OUT (C),%s'%R[yy]
   elif zz==2:t='%s HL,%s'%('ADC' if qq else 'SBC',['BC','DE','HL','SP'][pp])
   elif zz==3:
    nn=hx(word());rr=['BC','DE','HL','SP'][pp];t='LD %s,%s'%((rr,'('+nn+')') if qq else ('('+nn+')',rr))
   elif zz==4:t='NEG'
   elif zz==5:t='RETI' if yy==1 else 'RETN'
   elif zz==6:t='IM '+str([0,0,1,2,0,0,1,2][yy])
   else:t=['LD I,A','LD R,A','LD A,I','LD A,R','RRD','RLD','NOP','NOP'][yy]
  elif xx==2 and yy>=4 and zz<=3:t=[['LDI','CPI','INI','OUTI'],['LDD','CPD','IND','OUTD'],['LDIR','CPIR','INIR','OTIR'],['LDDR','CPDR','INDR','OTDR']][yy-4][zz]
  else:t='NOP/ED%02X'%o
 elif x==0:
  if z==0:
   if y<2:t=['NOP',"EX AF,AF'"][y]
   else:
    d=byte();dest=hx((p+(d if d<128 else d-256))&65535);t=('DJNZ ' if y==2 else 'JR ' if y==3 else 'JR '+CC[y-4]+',')+dest
  elif z==1:t='ADD %s,%s'%(hl,rp[a]) if q else 'LD %s,%s'%(rp[a],hx(word()))
  elif z==2:
   if y<4:t=['LD (BC),A','LD A,(BC)','LD (DE),A','LD A,(DE)'][y]
   else:
    nn='('+hx(word())+')';r=hl if y<6 else 'A';t='LD %s,%s'%((r,nn) if q else (nn,r))
  elif z==3:t='%s %s'%('DEC' if q else 'INC',rp[a])
  elif z in (4,5):t='%s %s'%('INC' if z==4 else 'DEC',reg(y))
  elif z==6:r=reg(y);t='LD %s,%02X'%(r,byte())
  else:t=['RLCA','RRCA','RLA','RRA','DAA','CPL','SCF','CCF'][y]
 elif x==1:
  if op==0x76:t='HALT'
  else:
   # LD H/L,(IX+d), LD (IX+d),H/L use ordinary H/L registers.
   if idx and (y==6 or z==6):mem=reg(6);t='LD %s,%s'%((mem,R[z]) if y==6 else (R[y],mem))
   else:t='LD %s,%s'%(reg(y),reg(z))
 elif x==2:t=['ADD A,','ADC A,','SUB ','SBC A,','AND ','XOR ','OR ','CP '][y]+reg(z)
 else:
  if z==0:t='RET '+CC[y]
  elif z==1:t='POP '+rp2[a] if not q else ['RET','EXX','JP ('+hl+')','LD SP,'+hl][a]
  elif z==2:t='JP '+CC[y]+','+hx(word())
  elif z==3:
   if y==0:t='JP '+hx(word())
   elif y in (2,3):n=byte();t=('OUT (%02X),A' if y==2 else 'IN A,(%02X)')%n
   else:t={4:'EX (SP),'+hl,5:'EX DE,HL',6:'DI',7:'EI'}.get(y,'PREFIX')
  elif z==4:t='CALL '+CC[y]+','+hx(word())
  elif z==5:t='PUSH '+rp2[a] if not q else 'CALL '+hx(word()) if a==0 else 'PREFIX'
  elif z==6:t=['ADD A,','ADC A,','SUB ','SBC A,','AND ','XOR ','OR ','CP '][y]+('%02X'%byte())
  else:t='RST %02X'%(y*8)
 return p,t

def listing(data,start,end):
 p=start
 while p<end:
  n,t=ins(data,p);yield '%04X  %-15s %s'%(p,data[p:n].hex(' '),t);p=n

def main():
 import argparse
 from pathlib import Path
 import rom_tables
 import euro_tables
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--rom',type=Path,required=True)
 parser.add_argument('--game',choices=(*rom_tables.LAYOUTS,*euro_tables.LAYOUTS),required=True)
 parser.add_argument('--start',type=lambda s:int(s,0),required=True)
 parser.add_argument('--end',type=lambda s:int(s,0),required=True)
 args=parser.parse_args()
 module=euro_tables if args.game in euro_tables.LAYOUTS else rom_tables
 data=module.load(args.rom,args.game)
 if not 0<=args.start<args.end<=len(data):parser.error('Range must fit the program ROM')
 try:print('\n'.join(listing(data,args.start,args.end)))
 except IndexError:parser.error('Truncated instruction at the end of the program ROM')

if __name__=='__main__':main()
