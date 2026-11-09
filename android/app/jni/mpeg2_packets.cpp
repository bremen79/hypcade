/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "mpeg2_packets.h"
static_assert(sizeof(off_t)>=8,"MPEG-2 file offsets must remain 64-bit");
#include <cstring>
#include <stdexcept>
#include <algorithm>
Mpeg2Packets::Mpeg2Packets(const char *path,uint64_t offset,const uint8_t *header,size_t header_size) {
    if(header_size>4096 || offset>INT64_MAX)throw std::runtime_error("Invalid MPEG-2 input");
    if(offset && header_size)prefix.assign(header,header+header_size);
    packet.reserve(65536);
    file=fopen(path,"rb");
    if(!file)throw std::runtime_error("Cannot open MPEG-2 input");
    if(fseeko(file,static_cast<off_t>(offset),SEEK_SET)){fclose(file);file=nullptr;throw std::runtime_error("Cannot seek MPEG-2 input");}
}
Mpeg2Packets::~Mpeg2Packets(){if(file)fclose(file);}
int Mpeg2Packets::byte() {
    if(pos==length){length=fread(input,1,sizeof(input),file);pos=0;
        if(!length){if(ferror(file))throw std::runtime_error("Cannot read MPEG-2 input");return -1;}}
    return input[pos++];
}
bool Mpeg2Packets::read(uint8_t *destination,size_t capacity,size_t &size,uint32_t &frame) {
    packet.clear();packet.insert(packet.end(),prefix.begin(),prefix.end());prefix.clear();
    bool picture=!pending.empty() && pending[3]==0;
    packet.insert(packet.end(),pending.begin(),pending.end());pending.clear();
    uint32_t code=0xffffffff;int value;
    while((value=byte())>=0) {
        if(packet.size()>=4*1024*1024)throw std::runtime_error("Oversized MPEG-2 picture");
        packet.push_back(static_cast<uint8_t>(value));code=(code<<8)|value;
        if((code&0xffffff00)==0x100 && (value==0 || value==0xb3 || value==0xb8)) {
            if(picture){pending.assign(packet.end()-4,packet.end());packet.resize(packet.size()-4);break;}
            if(value==0)picture=true;
        }
    }
    if(!picture)return false;
    bool found=false;
    for(size_t i=0;i+5<packet.size();++i)if(packet[i]==0 && packet[i+1]==0 && packet[i+2]==1) {
        if(packet[i+3]==0xb8)gop=static_cast<uint64_t>(highest+1);
        if(packet[i+3]==0){uint64_t index=gop+(packet[i+4]<<2)+(packet[i+5]>>6);
            if(index>UINT32_MAX)throw std::runtime_error("MPEG-2 timestamp overflow");
            frame=static_cast<uint32_t>(index);highest=std::max<int64_t>(highest,index);found=true;break;}
    }
    if(!found || !destination || packet.size()>capacity)throw std::runtime_error("Invalid or oversized codec packet");
    size=packet.size();memcpy(destination,packet.data(),size);return true;
}
#ifdef __ANDROID__
#include <jni.h>
static void fail(JNIEnv *e,const char *message){jclass c=e->FindClass("java/io/IOException");if(c){e->ThrowNew(c,message);e->DeleteLocalRef(c);}}
extern "C" JNIEXPORT jlong JNICALL Java_org_hypseus_android_Mpeg2PacketReader_open(JNIEnv *e,jclass,jstring path,jlong offset,jbyteArray header) {
    const char *name=e->GetStringUTFChars(path,nullptr);if(!name)return 0;
    jlong result=0;
    try {jsize n=e->GetArrayLength(header);if(n>4096)throw std::runtime_error("Oversized sequence header");
        std::vector<uint8_t> bytes(n);e->GetByteArrayRegion(header,0,n,reinterpret_cast<jbyte *>(bytes.data()));
        if(!e->ExceptionCheck())result=reinterpret_cast<jlong>(new Mpeg2Packets(name,offset,bytes.data(),bytes.size()));
    }catch(const std::exception &error){fail(e,error.what());}
    e->ReleaseStringUTFChars(path,name);return result;
}
extern "C" JNIEXPORT jlong JNICALL Java_org_hypseus_android_Mpeg2PacketReader_read(JNIEnv *e,jclass,jlong handle,jobject buffer) {
    try {auto *reader=reinterpret_cast<Mpeg2Packets *>(handle);auto *data=static_cast<uint8_t *>(e->GetDirectBufferAddress(buffer));
        jlong capacity=e->GetDirectBufferCapacity(buffer);if(!reader || capacity<=0)throw std::runtime_error("Invalid codec input buffer");
        size_t size=0;uint32_t frame=0;if(!reader->read(data,static_cast<size_t>(capacity),size,frame))return -1;
        return static_cast<jlong>((static_cast<uint64_t>(frame)<<32)|size);
    }catch(const std::exception &error){fail(e,error.what());return -1;}
}
extern "C" JNIEXPORT void JNICALL Java_org_hypseus_android_Mpeg2PacketReader_close(JNIEnv *,jclass,jlong handle) {delete reinterpret_cast<Mpeg2Packets *>(handle);}
#endif
