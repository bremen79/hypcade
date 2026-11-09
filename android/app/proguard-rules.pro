# SDL's C code looks up these Java classes and callbacks by literal name/signature.
# Keep the pinned Android integration intact; optimize the launcher around it.
-keep class org.libsdl.app.** { *; }

# JNI exports in android_bridge.cpp and arcade_guidance.cpp use this class name.
-keepnames class org.hypseus.android.HypseusActivity
-keepclassmembers class org.hypseus.android.HypseusActivity {
    native <methods>;
}

# Retain useful crash locations; keep mapping.txt with validation artifacts.
-keepattributes SourceFile,LineNumberTable

# Native MPEG-2 backend resolves this class and these methods by JNI names.
-keep class org.hypseus.android.Mpeg2HardwareDecoder { public *; }
-keep class org.hypseus.android.Mpeg2PacketReader { public *; }
