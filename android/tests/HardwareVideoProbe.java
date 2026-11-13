/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
import org.hypseus.android.Mpeg2HardwareDecoder;
import java.io.*;import java.nio.*;import java.util.*;
public class HardwareVideoProbe {
 public static void main(String[] args)throws Exception {
  System.load(args[0]);args=Arrays.copyOfRange(args,1,args.length);
  byte[] all=java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(args[0]));
  int gop=0;while(gop+4<all.length && !(all[gop]==0&&all[gop+1]==0&&all[gop+2]==1&&(all[gop+3]&255)==0xb8))gop++;
  byte[] header=Arrays.copyOf(all,gop);ByteBuffer image=ByteBuffer.allocateDirect(720*480*3/2);
  Mpeg2HardwareDecoder decoder=Mpeg2HardwareDecoder.open(args[0],0,header,720,480);
  if(decoder==null)throw new Exception("No hardware decoder");
  try(DataOutputStream output=new DataOutputStream(new BufferedOutputStream(new FileOutputStream(args[1])))) {
   for(int arg=2;arg<args.length;arg++) {
    long offset=Long.parseLong(args[arg]);if(!decoder.seek(offset,header))throw new Exception("seek");
    long start=System.nanoTime();int count=0;
    for(int frame=0;frame<10;frame++) {
     if(!decoder.next(image,720,480))break;
     output.writeLong(offset);output.writeInt(frame);
     for(int y=0;y<480;y+=16)for(int x=0;x<720;x+=16)output.writeByte(image.get(y*720+x));
     count++;
    }
    System.out.println("offset="+offset+" frames="+count+" ms="+(System.nanoTime()-start)/1000000);
   }
  }finally{decoder.close();}
 }
}
