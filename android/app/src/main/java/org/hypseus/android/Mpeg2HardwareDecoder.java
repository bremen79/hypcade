/* SPDX-License-Identifier: GPL-3.0-or-later
 * Hypcade Android MPEG-2 hardware decoding, 2026-11-09. */
package org.hypseus.android;

import android.graphics.Rect;
import android.media.Image;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaFormat;
import android.os.Build;
import android.util.Log;
import java.io.IOException;
import java.nio.ByteBuffer;

/** Decoder-thread-only, bounded-memory elementary-stream reader. No playback clock. */
public final class Mpeg2HardwareDecoder implements AutoCloseable {
    private static final String TAG = "HypcadeCodec";
    private final String path;
    private final int width, height;
    private MediaCodec codec;
    private long reader;
    private long presentationFrame;
    public long presentationFrame() { return presentationFrame; }
    private boolean inputEnd, outputEnd;
    private final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();

    private Mpeg2HardwareDecoder(String path, int width, int height) {
        this.path=path; this.width=width; this.height=height;
    }
    public static Mpeg2HardwareDecoder open(String path, long offset, byte[] header, int width, int height) {
        if (width<=0 || height<=0 || width>2048 || height>1088 || (width&1)!=0 || (height&1)!=0) return null;
        try {
            MediaFormat format=MediaFormat.createVideoFormat("video/mpeg2",width,height);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible);
            for (MediaCodecInfo candidate : new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos()) {
                if (candidate.isEncoder()) continue;
                String name=candidate.getName();
                if (Build.VERSION.SDK_INT>=29 ? !candidate.isHardwareAccelerated()
                        : name.startsWith("OMX.google.") || name.startsWith("c2.android.")) continue;
                for (String type : candidate.getSupportedTypes()) {
                    if (!type.equals("video/mpeg2")) continue;
                    MediaCodecInfo.CodecCapabilities caps=candidate.getCapabilitiesForType(type);
                    boolean flexible=false;
                    for(int color:caps.colorFormats) if(color==MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible) flexible=true;
                    if(!flexible || !caps.isFormatSupported(format)) continue;
                    Mpeg2HardwareDecoder result=new Mpeg2HardwareDecoder(path,width,height);
                    try {
                        result.codec=MediaCodec.createByCodecName(name);
                        result.codec.configure(format,null,null,0);
                        result.codec.start();
                        result.position(offset,header);
                        Log.i(TAG,"Hardware MPEG-2: "+name+" "+width+"x"+height);
                        return result;
                    } catch(Exception failure) { result.close();Log.w(TAG,"Decoder unavailable: "+name,failure); }
                }
            }
        } catch(Exception failure) { Log.w(TAG,"Hardware discovery unavailable",failure); }
        return null;
    }
    private void position(long offset, byte[] header) throws IOException {
        if(reader!=0){Mpeg2PacketReader.close(reader);reader=0;}
        reader=Mpeg2PacketReader.open(path,offset,header);
        if(reader==0)throw new IOException("Cannot open compressed video");
        inputEnd=outputEnd=false;
    }
    public boolean seek(long offset, byte[] header) {
        try {codec.flush();position(offset,header);return true;}
        catch(Exception failure){Log.w(TAG,"Hardware seek failed",failure);return false;}
    }
    public boolean next(ByteBuffer target, int stride, int rows) {
        if(outputEnd) return false;
        long deadline=System.nanoTime()+2_000_000_000L;
        try {
            while(System.nanoTime()<deadline) {
                if(!inputEnd) {
                    int input=codec.dequeueInputBuffer(0);
                    if(input>=0) {
                        ByteBuffer buffer=codec.getInputBuffer(input);
                        if(buffer==null)throw new IOException("Missing codec input buffer");
                        buffer.clear();long packet=Mpeg2PacketReader.read(reader,buffer);
                        if(packet==-1){codec.queueInputBuffer(input,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);inputEnd=true;}
                        else {
                            // Presentation ordering tags only; VLDP owns the playback clock.
                            codec.queueInputBuffer(input,0,(int)packet,(packet>>>32)*33367L,0);
                        }
                    }
                }
                int output=codec.dequeueOutputBuffer(info,1000);
                if(output>=0) {
                    try {
                        outputEnd=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;
                        if(info.size>0) {
                            try(Image image=codec.getOutputImage(output)) {
                                if(image==null) throw new IOException("No readable YUV image");
                                copy(image,target,stride,rows);
                            }
                            presentationFrame=info.presentationTimeUs/33367L;
                            return true;
                        }
                    } finally {codec.releaseOutputBuffer(output,false);}
                    if(outputEnd) return false;
                }
            }
            Log.w(TAG,"Hardware frame timed out; use software decoder");
        } catch(Exception failure){Log.w(TAG,"Hardware frame failed; use software decoder",failure);}
        return false;
    }
    private void copy(Image image, ByteBuffer target, int stride, int rows) throws IOException {
        Rect crop=image.getCropRect();
        if(crop.width()!=width || crop.height()!=height || image.getPlanes().length!=3
                || stride<width || rows<height || target.capacity()<stride*rows*3/2)
            throw new IOException("Unexpected YUV layout");
        Image.Plane[] planes=image.getPlanes();
        for(int plane=0;plane<3;plane++) {
            int shift=plane==0?0:1, w=width>>shift, h=height>>shift;
            int pitch=stride>>shift, offset=plane==0?0:stride*rows+(plane-1)*(stride/2)*(rows/2);
            Image.Plane p=planes[plane];ByteBuffer source=p.getBuffer();
            int base=source.position()+(crop.top>>shift)*p.getRowStride()+(crop.left>>shift)*p.getPixelStride();
            if(p.getPixelStride()==1 && p.getRowStride()==pitch && pitch==w) {
                source.limit(base+w*h);source.position(base);target.position(offset);target.put(source);
            } else for(int y=0;y<h;y++) {
                int from=base+y*p.getRowStride();target.position(offset+y*pitch);
                if(p.getPixelStride()==1){source.limit(from+w);source.position(from);target.put(source);source.clear();}
                else for(int x=0;x<w;x++)target.put(source.get(from+x*p.getPixelStride()));
            }
        }
        target.clear();
    }
    @Override public void close() {
        if(reader!=0){Mpeg2PacketReader.close(reader);reader=0;}
        if(codec!=null){try{codec.stop();}catch(Exception ignored){}finally{codec.release();codec=null;}}
    }
}
