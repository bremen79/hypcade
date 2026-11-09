/* SPDX-License-Identifier: GPL-3.0-or-later
 * Hypcade hardware video bridge, 2026-11-09. All decoder calls stay on VLDP's thread. */
#include "android_video_codec.h"
#include <SDL3/SDL.h>
#include <jni.h>
#include <vector>
#include <string>
#include <algorithm>
static jclass decoder_class=nullptr;
static jmethodID open_method, seek_method, next_method, close_method, frame_method;
static jobject decoder=nullptr, buffer=nullptr;
static std::vector<uint8_t> pixels;
static std::string filename;
static int pitch=0, rows=0;
static bool enabled=false, prefetched=false;
static int64_t expected_frame=-1;
static JNIEnv *env() { return static_cast<JNIEnv *>(SDL_GetAndroidJNIEnv()); }
static bool exception(JNIEnv *e) {
    if(!e->ExceptionCheck()) return false;
    e->ExceptionClear(); return true;
}
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeConfigureVideo(JNIEnv *e, jclass, jboolean allow)
{
    enabled=false;
    if(!allow) return;
    if(!decoder_class) {
        jclass local=e->FindClass("org/hypseus/android/Mpeg2HardwareDecoder");
        if(exception(e) || !local) return;
        decoder_class=static_cast<jclass>(e->NewGlobalRef(local));e->DeleteLocalRef(local);
        if(!decoder_class || exception(e))return;
        open_method=e->GetStaticMethodID(decoder_class,"open","(Ljava/lang/String;J[BII)Lorg/hypseus/android/Mpeg2HardwareDecoder;");
        seek_method=e->GetMethodID(decoder_class,"seek","(J[B)Z");
        next_method=e->GetMethodID(decoder_class,"next","(Ljava/nio/ByteBuffer;II)Z");
        close_method=e->GetMethodID(decoder_class,"close","()V");
        frame_method=e->GetMethodID(decoder_class,"presentationFrame","()J");
        if(exception(e) || !open_method || !seek_method || !next_method || !close_method || !frame_method) return;
    }
    enabled=true;
}
void android_video_disable() { enabled=false; }
void android_video_close() {
    JNIEnv *e=env();
    if(decoder){e->CallVoidMethod(decoder,close_method);exception(e);e->DeleteGlobalRef(decoder);decoder=nullptr;}
    if(buffer){e->DeleteGlobalRef(buffer);buffer=nullptr;}
    pixels.clear();filename.clear();prefetched=false;
}
bool android_video_start(const char *path, uint64_t offset, const uint8_t *header, size_t size, int width, int height) {
    if(!enabled || !path || width<=0 || height<=0 || width>2048 || height>1088) return false;
    JNIEnv *e=env();jbyteArray bytes=e->NewByteArray(static_cast<jsize>(size));
    if(!bytes || exception(e))return false;
    e->SetByteArrayRegion(bytes,0,static_cast<jsize>(size),reinterpret_cast<const jbyte *>(header));
    bool ok=false;
    if(decoder && filename==path && pitch==((width+15)&~15) && rows==((height+15)&~15)) {
        ok=e->CallBooleanMethod(decoder,seek_method,static_cast<jlong>(offset),bytes);
        if(exception(e))ok=false;
    } else {
        android_video_close();
        jstring name=e->NewStringUTF(path);
        jobject local=e->CallStaticObjectMethod(decoder_class,open_method,name,static_cast<jlong>(offset),bytes,width,height);
        e->DeleteLocalRef(name);
        if(!exception(e) && local) {
            decoder=e->NewGlobalRef(local);e->DeleteLocalRef(local);filename=path;
            pitch=(width+15)&~15;rows=(height+15)&~15;
            pixels.assign(static_cast<size_t>(pitch)*rows*3/2,128);
            std::fill(pixels.begin(),pixels.begin()+pitch*rows,16);
            jobject direct=e->NewDirectByteBuffer(pixels.data(),pixels.size());
            buffer=e->NewGlobalRef(direct);e->DeleteLocalRef(direct);ok=buffer!=nullptr;
        }
    }
    e->DeleteLocalRef(bytes);
    prefetched=false;expected_frame=-1;
    if(ok) {ok=e->CallBooleanMethod(decoder,next_method,buffer,pitch,rows);if(exception(e))ok=false;}
    if(!ok){android_video_close();return false;}
    prefetched=true;return true;
}
const uint8_t *android_video_next(int first_temporal_reference) {
    if(!decoder)return nullptr;
    JNIEnv *e=env();
    for(int attempts=0;attempts<64;++attempts) {
        bool ok=prefetched;prefetched=false;
        if(!ok){ok=e->CallBooleanMethod(decoder,next_method,buffer,pitch,rows);if(exception(e))ok=false;}
        if(!ok)return nullptr;
        jlong frame=e->CallLongMethod(decoder,frame_method);
        if(exception(e))return nullptr;
        if(first_temporal_reference>=0) expected_frame=first_temporal_reference;
        if(frame==expected_frame){++expected_frame;return pixels.data();}
        if(first_temporal_reference<0 || frame>expected_frame)return nullptr;
        // A vendor may emit rather than discard broken leading B pictures.
        // Drop those here too, matching VLDP's skipped preroll exactly.
    }
    return nullptr;
}
