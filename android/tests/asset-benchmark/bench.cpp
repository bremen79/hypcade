/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <jni.h>
#include <android/asset_manager_jni.h>
#include <chrono>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>
#include <sstream>
#include <cstdint>
#include <algorithm>
using Clock=std::chrono::steady_clock;
struct File {std::string name; size_t size;};
static uint64_t hash(const std::vector<unsigned char>& bytes) {
    uint64_t h=14695981039346656037ULL;
    for(auto b:bytes) {h^=b;h*=1099511628211ULL;} return h;
}
extern "C" JNIEXPORT jstring JNICALL Java_org_hypcade_assetbench_Main_run(
    JNIEnv* env,jclass,jobject manager,jstring directory,jobjectArray paths) {
 try {
    auto* assets=AAssetManager_fromJava(env,manager);
    const char* raw=env->GetStringUTFChars(directory,nullptr);std::string root(raw);env->ReleaseStringUTFChars(directory,raw);
    std::vector<File> all;
    for(int i=0;i<env->GetArrayLength(paths);i++) {
        auto s=(jstring)env->GetObjectArrayElement(paths,i);const char* p=env->GetStringUTFChars(s,nullptr);
        auto* a=AAssetManager_open(assets,p,AASSET_MODE_UNKNOWN);if(!a) throw std::runtime_error("open asset");
        all.push_back({p,(size_t)AAsset_getLength64(a)});AAsset_close(a);
        env->ReleaseStringUTFChars(s,p);env->DeleteLocalRef(s);
    }
    std::ostringstream out;out<<"case,pass,backend,bytes,milliseconds,checksum\n";
    for(const std::string scenario:{"all","sound","pics","fonts","seek_png","seek_bmp"}) {
        bool seek=scenario.find("seek_")==0;
        std::vector<File> files;
        for(auto f:all) {
            if(scenario=="all" || f.name.find("hypseus/"+scenario+"/")==0) files.push_back(f);
            if(seek && f.name.size()>4 && f.name.substr(f.name.size()-4)==(scenario=="seek_png"?".png":".bmp"))
                if(files.empty() || f.size>files[0].size) files={f};
        }
        if(files.empty()) throw std::runtime_error("empty scenario");
        size_t bytes=0;for(auto f:files) bytes+=f.size;
        if(seek) bytes=256*4096;
        std::vector<unsigned char> output(bytes);
        uint64_t expected=0;
        for(int pass=0;pass<31;pass++) for(int order=0;order<2;order++) {
            bool apk=(order==(pass%2));size_t offset=0;
            auto start=Clock::now();
            for(auto f:files) {
                AAsset* a=apk?AAssetManager_open(assets,f.name.c_str(),AASSET_MODE_UNKNOWN):nullptr;
                FILE* disk=apk?nullptr:fopen((root+"/"+f.name).c_str(),"rb");
                if((apk&&!a)||(!apk&&!disk)) throw std::runtime_error("open");
                int count=seek?256:1;
                for(int n=0;n<count;n++) {
                    size_t remaining=seek?4096:f.size;
                    if(seek) {
                        // Deterministic non-monotonic reads, including repeated backward seeks.
                        size_t pos=((uint64_t)n*2654435761ULL)%(f.size-4096);
                        if(apk ? AAsset_seek64(a,pos,SEEK_SET)<0 : fseek(disk,pos,SEEK_SET)!=0) throw std::runtime_error("seek");
                    }
                    while(remaining) {
                        size_t want=std::min(remaining,(size_t)65536);
                        int got=apk?AAsset_read(a,output.data()+offset,want):(int)fread(output.data()+offset,1,want,disk);
                        if(got<=0) throw std::runtime_error("read");
                        remaining-=got;offset+=got;
                    }
                }
                if(apk) AAsset_close(a);else fclose(disk);
            }
            double ms=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
            uint64_t checksum=hash(output); // Outside the measured interval.
            if(pass==0 && order==0) expected=checksum;
            if(checksum!=expected) throw std::runtime_error("checksum mismatch");
            out<<scenario<<","<<pass<<","<<(apk?"apk":"file")<<","<<bytes<<","<<ms<<","<<checksum<<"\n";
        }
    }
    return env->NewStringUTF(out.str().c_str());
 } catch(const std::exception& e) {return env->NewStringUTF((std::string("ERROR: ")+e.what()).c_str());}
}
