# Arcade1Up Yoga Flame: ADB capability inspection

This Yoga Flame cabinet runs a 32-bit Android 10 system on a MediaTek MT8168,
with about 935 MiB of memory visible to the kernel and a 1280 × 960 display.
Its driver advertises hardware MPEG-2 decoding and OpenGL ES 3.2.

| Item | Reported value |
| --- | --- |
| Product/model | vnd_tb8168p1_bsp / P71 |
| SoC | MediaTek MT8168 |
| OS | Android 10, API 29 |
| Android application ABIs | armeabi-v7a, armeabi (32-bit OS) |
| CPU | ARM CPU part 0xd03; NEON present; maximum frequency 2,001,000 kHz |
| Kernel-visible RAM | 957,692 KiB (about 935 MiB) |
| Display | 1280 × 960, 4:3; one advertised mode, 63.45 Hz |
| GPU / GL driver | ARM Mali-G52 MC2; OpenGL ES 3.2, r20p0-01rel0 |
| Relevant GPU extensions | GL_OES_EGL_image_external, GL_OES_EGL_image_external_essl3, GL_EXT_YUV_target |
| Vendor MPEG-2 decoder | OMX.MTK.VIDEO.DECODER.MPEG2, video/mpeg2 |
| MPEG-2 size limits | 16×16 through 2048×1088 |
| MPEG-2 advertised performance point | 1920×1088 at 30 fps |

`/vendor/etc/media_codecs.xml` includes
`media_codecs_mediatek_video.xml`, which contains the MPEG-2 entry above.
The vendor also lists AVC, HEVC, MPEG-4, H.263, VC-1, Xvid, VP8 and VP9 decoders.
These are configuration declarations, not measured decoding results.
`dumpsys media.codec` is unavailable on this firmware; inspection used vendor
XML, display/SurfaceFlinger dumps and read-only system properties instead.

Use the ARMv7 arcade APK on this OS. The panel mode is 1280×960.

## Hardware MPEG-2 decoding

`OMX.MTK.VIDEO.DECODER.MPEG2` provides readable YUV output. Its runtime
capability query reports a maximum width of 1920, despite the XML declaration
of 2048; the advertised XML limits must not override the runtime query.

The production packet-reader/Java-decoder probe covered 172 sampled seek frames
from generated 720×480 progressive and interlaced MPEG-2 streams, including
open-GOP preroll. Sparse luma comparisons against libmpeg2 had a worst mean
error below 0.009/255. This establishes sampled image agreement, not every pixel
or support for all MPEG profiles.

A 90-frame production-backend probe took 635–787 ms per pass, with 192–216 ms
of decoder-thread CPU time. These are synthetic decode-only measurements;
they do not establish end-to-end gameplay speed or total-system CPU savings.

Hardware decoding is automatic and retains the software fallback for unsupported
hardware/streams and very short clips. There is no per-game decoder switch.
The build minimum is API 25; the system described here is API 29.

Inspection date: November 9, 2026. Raw device dumps remain local and are not
part of the public repository. The properties above describe this model and
firmware; they are not declarations for every Arcade1Up system.
